import os
import sys
import json
from http.server import BaseHTTPRequestHandler
from http import HTTPStatus
from datetime import datetime, timezone

# Add parent directory to sys.path
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
    """Vercel Serverless Function Handler specifically for /api/chat."""

    def _send_json_response(self, data, status_code=HTTPStatus.OK):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, apikey")
        self.end_headers()
        json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.wfile.write(json_bytes)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, apikey")
        self.end_headers()

    def do_GET(self):
        return self._send_json_response({
            "status": "healthy",
            "service": "GujaratEdu Chat API",
            "institutions_loaded": len(INSTITUTIONS)
        })

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length) if content_length > 0 else b""
        try:
            payload = json.loads(post_body.decode("utf-8")) if post_body else {}
        except Exception:
            payload = {}

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
