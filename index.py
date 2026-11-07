import os
import sys
import json
import mimetypes
from http.server import BaseHTTPRequestHandler
from http import HTTPStatus
from datetime import datetime, timezone

# Add root directory to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from gujarat_college_bot import answer_query, INSTITUTIONS
except Exception as e:
    INSTITUTIONS = []
    def answer_query(q):
        return None

try:
    from app import (
        get_supabase_config,
        save_supabase_config,
        supabase_api_request,
        save_chat_record_to_supabase
    )
except Exception:
    def get_supabase_config():
        return {"configured": False, "url": "", "key": ""}
    def save_supabase_config(u, k):
        pass
    def supabase_api_request(*args, **kwargs):
        return {"status": "error", "error": "Supabase not configured"}
    def save_chat_record_to_supabase(*args, **kwargs):
        return False, "Not configured"

class handler(BaseHTTPRequestHandler):
    """Vercel Serverless Function Handler for GujaratEdu APIs."""

    def _send_json_response(self, data, status_code=HTTPStatus.OK):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, apikey")
        self.end_headers()
        json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.wfile.write(json_bytes)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, apikey")
        self.end_headers()

    def do_GET(self):
        clean_path = self.path.split("?")[0].rstrip("/")

        # 1. Serve Homepage if accessed directly or routed to root
        if clean_path in ("", "/", "/index", "/index.html"):
            for candidate in [os.path.join(ROOT_DIR, "index.html"), os.path.join(ROOT_DIR, "static", "index.html")]:
                if os.path.isfile(candidate):
                    with open(candidate, "rb") as f:
                        html_bytes = f.read()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "public, max-age=0, must-revalidate")
                    self.end_headers()
                    self.wfile.write(html_bytes)
                    return

        # 2. API Endpoints
        if clean_path.endswith("/api/health") or clean_path in ("/api", "/health"):
            return self._send_json_response({
                "status": "healthy",
                "service": "GujaratEdu Vercel Serverless API",
                "institutions_loaded": len(INSTITUTIONS)
            })

        if clean_path.endswith("/api/colleges") or clean_path == "/colleges":
            return self._send_json_response({
                "count": len(INSTITUTIONS),
                "institutions": INSTITUTIONS
            })

        if clean_path.endswith("/api/stats") or clean_path == "/stats":
            g_count = sum(1 for i in INSTITUTIONS if "Government" in i.get("type", ""))
            p_count = sum(1 for i in INSTITUTIONS if "Private" in i.get("type", ""))
            return self._send_json_response({
                "total_institutions": len(INSTITUTIONS),
                "government_colleges": g_count,
                "private_universities": p_count
            })

        if clean_path.endswith("/api/supabase/config"):
            cfg = get_supabase_config()
            return self._send_json_response({
                "configured": cfg["configured"],
                "supabase_url": cfg["url"],
                "masked_key": f"{cfg['key'][:8]}...{cfg['key'][-6:]}" if cfg["configured"] and len(cfg["key"]) > 16 else ""
            })

        if clean_path.endswith("/api/supabase/history"):
            cfg = get_supabase_config()
            if not cfg["configured"]:
                return self._send_json_response({"status": "success", "data": []})
            res = supabase_api_request("chat_history?order=created_at.asc")
            return self._send_json_response(res)

        # 3. Static Assets Fallback (style.css, app.js, knowledge.js, etc.)
        rel_path = clean_path.lstrip("/")
        for base in [ROOT_DIR, os.path.join(ROOT_DIR, "static")]:
            target_file = os.path.join(base, rel_path)
            if os.path.isfile(target_file):
                content_type, _ = mimetypes.guess_type(target_file)
                with open(target_file, "rb") as f:
                    file_bytes = f.read()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type or "application/octet-stream")
                self.end_headers()
                self.wfile.write(file_bytes)
                return

        return self._send_json_response({"error": "Endpoint not found"}, status_code=HTTPStatus.NOT_FOUND)

    def do_POST(self):
        clean_path = self.path.split("?")[0].rstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length) if content_length > 0 else b""
        try:
            payload = json.loads(post_body.decode("utf-8")) if post_body else {}
        except Exception:
            payload = {}

        if clean_path.endswith("/api/chat") or clean_path == "/chat":
            query = payload.get("query", "").strip()
            session_id = payload.get("session_id")
            session_title = payload.get("session_title")

            if not query:
                return self._send_json_response({
                    "status": "error",
                    "answer": "Please ask a question regarding higher education after 12th Science in Gujarat."
                })

            try:
                answer = answer_query(query)
                success = True
            except Exception as ex:
                answer = f"Error generating answer: {ex}"
                success = False

            now_utc = datetime.now(timezone.utc)
            created_at = now_utc.isoformat()
            date_str = now_utc.strftime("%d %b %Y, %I:%M %p")

            cfg = get_supabase_config()
            client_url = payload.get("supabase_url") or cfg["url"]
            client_key = payload.get("supabase_key") or cfg["key"]

            supabase_saved = False
            if (cfg["configured"] or (client_url and client_key)) and success and answer:
                try:
                    s_id = session_id or f"chat_{int(now_utc.timestamp())}"
                    s_title = session_title or (query[:45] + "..." if len(query) > 45 else query)
                    ok1, _ = save_chat_record_to_supabase(s_id, s_title, "user", query, created_at, date_str, override_url=client_url, override_key=client_key)
                    ok2, _ = save_chat_record_to_supabase(s_id, s_title, "bot", answer, created_at, date_str, override_url=client_url, override_key=client_key)
                    supabase_saved = (ok1 and ok2)
                except Exception:
                    pass

            return self._send_json_response({
                "status": "success" if success else "error",
                "answer": answer,
                "created_at": created_at,
                "date_str": date_str,
                "supabase_saved": supabase_saved
            })

        if clean_path.endswith("/api/supabase/test"):
            test_url = payload.get("supabase_url", "").strip()
            test_key = payload.get("supabase_key", "").strip()
            res = supabase_api_request("chat_history?limit=1", method="GET", override_url=test_url, override_key=test_key)
            return self._send_json_response(res)

        if clean_path.endswith("/api/supabase/delete_session"):
            s_id = payload.get("session_id")
            c_url = payload.get("supabase_url")
            c_key = payload.get("supabase_key")
            if not s_id:
                return self._send_json_response({"status": "error", "error": "session_id required"}, status_code=HTTPStatus.BAD_REQUEST)
            res = supabase_api_request(f"chat_history?session_id=eq.{s_id}", method="DELETE", override_url=c_url, override_key=c_key)
            return self._send_json_response(res)

        if clean_path.endswith("/api/supabase/clear_all"):
            c_url = payload.get("supabase_url")
            c_key = payload.get("supabase_key")
            res = supabase_api_request("chat_history?id=neq.00000000-0000-0000-0000-000000000000", method="DELETE", override_url=c_url, override_key=c_key)
            return self._send_json_response(res)

        return self._send_json_response({"error": "Endpoint not found"}, status_code=HTTPStatus.NOT_FOUND)
