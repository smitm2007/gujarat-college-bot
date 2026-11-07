import os
import sys
import json
import mimetypes
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import webbrowser

# Ensure UTF-8 output & line buffering
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Import the core bot QA engine
try:
    from gujarat_college_bot import answer_query, INSTITUTIONS
    print(f"[GujaratEdu Server] Core QA engine loaded successfully. {len(INSTITUTIONS)} institutions registered.")
except Exception as e:
    print(f"[GujaratEdu Server Error] Could not load gujarat_college_bot: {e}")
    answer_query = lambda q: f"Error loading QA engine: {e}"
    INSTITUTIONS = []

STATIC_DIR = CURRENT_DIR
if os.path.exists(os.path.join(CURRENT_DIR, "static", "index.html")) and not os.path.exists(os.path.join(CURRENT_DIR, "index.html")):
    STATIC_DIR = os.path.join(CURRENT_DIR, "static")

SUPABASE_CONFIG_PATH = os.path.join(CURRENT_DIR, "supabase_config.json")

# Optional requests library for HTTP calls
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error

# ==============================================================================
# SUPABASE CONFIG & OPERATIONS HELPERS
# ==============================================================================

def get_supabase_config():
    """Load Supabase configuration from environment or supabase_config.json."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()

    if not url or not key:
        if os.path.exists(SUPABASE_CONFIG_PATH):
            try:
                with open(SUPABASE_CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    url = url or cfg.get("supabase_url", "").strip()
                    key = key or cfg.get("supabase_key", "").strip()
            except Exception as e:
                print(f"[Supabase Config Warning] Could not parse supabase_config.json: {e}")

    configured = bool(url and key and url.startswith("http"))
    return {
        "url": url,
        "key": key,
        "configured": configured
    }

def save_supabase_config(url, key):
    """Save Supabase configuration to supabase_config.json."""
    data = {
        "supabase_url": (url or "").strip(),
        "supabase_key": (key or "").strip()
    }
    with open(SUPABASE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True

def supabase_api_request(endpoint, method="GET", payload=None, timeout=8, override_url=None, override_key=None):
    """Perform direct HTTPS request to Supabase PostgREST API."""
    cfg = get_supabase_config()
    url = (override_url or cfg["url"]).strip()
    key = (override_key or cfg["key"]).strip()

    if not url or not key:
        return {"status": "error", "error": "Supabase credentials are not configured"}

    base_url = url.rstrip("/")
    target_url = f"{base_url}/rest/v1/{endpoint}"

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    if method in ("POST", "PUT", "PATCH"):
        headers["Prefer"] = "return=representation"

    if HAS_REQUESTS:
        try:
            if method == "GET":
                resp = requests.get(target_url, headers=headers, timeout=timeout)
            elif method == "POST":
                resp = requests.post(target_url, headers=headers, json=payload, timeout=timeout)
            elif method == "DELETE":
                resp = requests.delete(target_url, headers=headers, timeout=timeout)
            else:
                return {"status": "error", "error": f"Unsupported HTTP method: {method}"}

            if resp.status_code >= 400:
                return {
                    "status": "error",
                    "code": resp.status_code,
                    "error": resp.text
                }
            
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            return {"status": "success", "data": data, "code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    else:
        # Fallback to urllib.request
        try:
            data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
            req = urllib.request.Request(target_url, data=data_bytes, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                try:
                    data = json.loads(body)
                except Exception:
                    data = body
                return {"status": "success", "data": data, "code": response.status}
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8", errors="replace")
            return {"status": "error", "code": he.code, "error": err_body}
        except Exception as e:
            return {"status": "error", "error": str(e)}

def save_chat_record_to_supabase(session_id, session_title, role, message_text, created_at=None, date_str=None, override_url=None, override_key=None):
    """Persist a single chat record (question or answer) to Supabase chat_history table."""
    cfg = get_supabase_config()
    url = (override_url or cfg["url"]).strip()
    key = (override_key or cfg["key"]).strip()

    if not url or not key:
        return False, "Not configured (missing Supabase URL or Key)"

    now_utc = datetime.now(timezone.utc)
    if not created_at:
        created_at = now_utc.isoformat()
    if not date_str:
        date_str = now_utc.strftime("%d %b %Y, %I:%M %p UTC")

    payload = {
        "session_id": str(session_id or f"chat_{int(now_utc.timestamp())}"),
        "session_title": str(session_title or message_text[:48] or "Consultation"),
        "role": str(role),
        "message_text": str(message_text),
        "created_at": created_at,
        "date_str": date_str
    }

    res = supabase_api_request("chat_history", method="POST", payload=payload, override_url=url, override_key=key)
    if res.get("status") == "success":
        print(f"[Supabase] Saved {role} message to chat_history ({payload['session_id']})")
        return True, res.get("data")
    else:
        err = res.get("error", "Unknown error")
        code = res.get("code")
        print(f"[Supabase Save Error HTTP {code}]: {err}")
        return False, err

# ==============================================================================
# HTTP HANDLER
# ==============================================================================

class GujaratEduHandler(SimpleHTTPRequestHandler):
    """Multi-threaded HTTP handler for GujaratEdu Frontend & Supabase REST API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, format, *args):
        # Format clean console logs
        sys.stdout.write(f"[{self.log_date_time_string()}] {self.command} {self.path} - {args[0]}\n")
        sys.stdout.flush()

    def do_OPTIONS(self):
        """Handle CORS pre-flight."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, apikey")
        self.end_headers()

    def _send_json_response(self, data, status_code=HTTPStatus.OK):
        """Helper to send JSON response with standard CORS headers."""
        resp_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, apikey")
        self.send_header("Content-Length", str(len(resp_bytes)))
        self.end_headers()
        self.wfile.write(resp_bytes)

    def do_POST(self):
        """Handle API requests."""
        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(post_body.decode("utf-8"))
        except Exception:
            payload = {}

        # -------------------------------------------------------------
        # 1. Main Chat Endpoint
        # -------------------------------------------------------------
        if self.path == "/api/chat":
            query = payload.get("query", "").strip()
            session_id = payload.get("session_id", "")
            session_title = payload.get("session_title", "")

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

            # Automatically persist chat history to Supabase if configured or if client provided keys
            cfg = get_supabase_config()
            client_url = payload.get("supabase_url") or cfg["url"]
            client_key = payload.get("supabase_key") or cfg["key"]

            if not cfg["configured"] and client_url and client_key:
                save_supabase_config(client_url, client_key)
                cfg = get_supabase_config()

            supabase_saved = False
            if (cfg["configured"] or (client_url and client_key)) and success:
                try:
                    s_id = session_id or f"chat_{int(now_utc.timestamp())}"
                    s_title = session_title or (query[:45] + "..." if len(query) > 45 else query)
                    # Save user query
                    ok1, r1 = save_chat_record_to_supabase(s_id, s_title, "user", query, created_at, date_str, override_url=client_url, override_key=client_key)
                    # Save bot answer
                    ok2, r2 = save_chat_record_to_supabase(s_id, s_title, "bot", answer, created_at, date_str, override_url=client_url, override_key=client_key)
                    supabase_saved = (ok1 and ok2)
                    if not supabase_saved:
                        print(f"[Supabase Auto-Save Warning]: user_ok={ok1} ({r1}), bot_ok={ok2} ({r2})")
                except Exception as se:
                    print(f"[Supabase Auto-Save Exception]: {se}")

            return self._send_json_response({
                "status": "success" if success else "error",
                "answer": answer,
                "created_at": created_at,
                "date_str": date_str,
                "supabase_saved": supabase_saved
            })

        # -------------------------------------------------------------
        # 2. Supabase Config (Save credentials)
        # -------------------------------------------------------------
        if self.path == "/api/supabase/config":
            new_url = payload.get("supabase_url", "").strip()
            new_key = payload.get("supabase_key", "").strip()
            save_supabase_config(new_url, new_key)
            cfg = get_supabase_config()
            print(f"[Supabase Config] Credentials saved. Configured: {cfg['configured']}")
            return self._send_json_response({
                "status": "success",
                "message": "Supabase configuration updated successfully.",
                "configured": cfg["configured"],
                "supabase_url": cfg["url"]
            })

        # -------------------------------------------------------------
        # 3. Supabase Test Connection (Deep Read & Write Test)
        # -------------------------------------------------------------
        if self.path == "/api/supabase/test":
            test_url = payload.get("supabase_url", "").strip()
            test_key = payload.get("supabase_key", "").strip()

            cfg = get_supabase_config()
            eff_url = test_url or cfg["url"]
            eff_key = test_key or cfg["key"]

            if not eff_url or not eff_key:
                return self._send_json_response({
                    "status": "error",
                    "connected": False,
                    "error": "Please provide both Supabase Project URL and Anon API Key."
                }, status_code=HTTPStatus.BAD_REQUEST)

            # 1. Test Read Access
            read_res = supabase_api_request("chat_history?limit=1", method="GET", override_url=eff_url, override_key=eff_key)
            if read_res.get("status") != "success":
                err_text = str(read_res.get("error", ""))
                code = read_res.get("code")
                # Table does not exist
                if code == 404 or "PGRST205" in err_text or "does not exist" in err_text:
                    return self._send_json_response({
                        "status": "error",
                        "connected": False,
                        "table_missing": True,
                        "code": 404,
                        "error": "Table 'public.chat_history' was NOT found in your Supabase project! Please run the SQL schema in your Supabase SQL Editor."
                    }, status_code=HTTPStatus.BAD_REQUEST)
                return self._send_json_response({
                    "status": "error",
                    "connected": False,
                    "code": code,
                    "error": f"Connection to Supabase failed: {err_text}"
                }, status_code=HTTPStatus.BAD_REQUEST)

            # 2. Test Write / Insert Access (checks Row Level Security policies)
            now_iso = datetime.now(timezone.utc).isoformat()
            test_payload = {
                "session_id": "_ping_test_",
                "session_title": "Connection Test",
                "role": "system",
                "message_text": "Ping verify write access",
                "created_at": now_iso,
                "date_str": "Test Date"
            }
            insert_res = supabase_api_request("chat_history", method="POST", payload=test_payload, override_url=eff_url, override_key=eff_key)
            
            if insert_res.get("status") == "success":
                # Immediately clean up the test row
                supabase_api_request("chat_history?session_id=eq._ping_test_", method="DELETE", override_url=eff_url, override_key=eff_key)
                if test_url and test_key:
                    save_supabase_config(test_url, test_key)
                return self._send_json_response({
                    "status": "success",
                    "connected": True,
                    "can_insert": True,
                    "message": "Full Read & Write connection to Supabase table 'chat_history' verified successfully!"
                })
            else:
                insert_err = str(insert_res.get("error", ""))
                ins_code = insert_res.get("code")
                rls_blocked = ("42501" in insert_err or "row-level security" in insert_err.lower() or ins_code == 403 or ins_code == 401)
                
                if rls_blocked:
                    return self._send_json_response({
                        "status": "error",
                        "connected": False,
                        "rls_blocked": True,
                        "code": 403,
                        "error": "Row-Level Security (RLS) is blocking inserts! To fix this in 1 click, run this SQL in Supabase SQL Editor:\n\nALTER TABLE public.chat_history DISABLE ROW LEVEL SECURITY;"
                    }, status_code=HTTPStatus.BAD_REQUEST)
                else:
                    return self._send_json_response({
                        "status": "error",
                        "connected": False,
                        "code": ins_code,
                        "error": f"Insert test failed: {insert_err}. Ensure table has columns: id, session_id, session_title, role, message_text, created_at, date_str."
                    }, status_code=HTTPStatus.BAD_REQUEST)

        # -------------------------------------------------------------
        # 4. Save Single Message to Supabase
        # -------------------------------------------------------------
        if self.path == "/api/supabase/save_message":
            s_id = payload.get("session_id")
            s_title = payload.get("session_title", "Consultation")
            role = payload.get("role", "user")
            text = payload.get("message_text", "")
            created_at = payload.get("created_at")
            date_str = payload.get("date_str")
            c_url = payload.get("supabase_url")
            c_key = payload.get("supabase_key")

            if c_url and c_key:
                curr_cfg = get_supabase_config()
                if not curr_cfg["configured"]:
                    save_supabase_config(c_url, c_key)

            ok, result = save_chat_record_to_supabase(s_id, s_title, role, text, created_at, date_str, override_url=c_url, override_key=c_key)
            if ok:
                return self._send_json_response({"status": "success", "result": result})
            else:
                return self._send_json_response({"status": "error", "error": str(result)}, status_code=HTTPStatus.BAD_REQUEST)

        # -------------------------------------------------------------
        # 5. Batch Sync History from Client to Supabase
        # -------------------------------------------------------------
        if self.path == "/api/supabase/sync_batch":
            messages = payload.get("messages", [])
            c_url = payload.get("supabase_url")
            c_key = payload.get("supabase_key")

            if c_url and c_key:
                curr_cfg = get_supabase_config()
                if not curr_cfg["configured"]:
                    save_supabase_config(c_url, c_key)

            saved_count = 0
            errors = []

            for m in messages:
                ok, res = save_chat_record_to_supabase(
                    session_id=m.get("session_id"),
                    session_title=m.get("session_title"),
                    role=m.get("role"),
                    message_text=m.get("message_text"),
                    created_at=m.get("created_at"),
                    date_str=m.get("date_str"),
                    override_url=c_url,
                    override_key=c_key
                )
                if ok:
                    saved_count += 1
                else:
                    errors.append(str(res))

            return self._send_json_response({
                "status": "success" if saved_count > 0 or len(messages) == 0 else "error",
                "saved_count": saved_count,
                "total_requested": len(messages),
                "errors": errors[:5]
            })

        # -------------------------------------------------------------
        # 6. Delete a session from Supabase
        # -------------------------------------------------------------
        if self.path == "/api/supabase/delete_session":
            session_id = payload.get("session_id")
            c_url = payload.get("supabase_url")
            c_key = payload.get("supabase_key")

            if not session_id:
                return self._send_json_response({"status": "error", "error": "session_id required"}, status_code=HTTPStatus.BAD_REQUEST)

            res = supabase_api_request(f"chat_history?session_id=eq.{session_id}", method="DELETE", override_url=c_url, override_key=c_key)
            print(f"[Supabase Delete] Removed session {session_id} from chat_history. Status: {res.get('status')}")
            return self._send_json_response(res)

        # -------------------------------------------------------------
        # 7. Clear all chat history from Supabase
        # -------------------------------------------------------------
        if self.path == "/api/supabase/clear_all":
            c_url = payload.get("supabase_url")
            c_key = payload.get("supabase_key")
            res = supabase_api_request("chat_history?id=neq.00000000-0000-0000-0000-000000000000", method="DELETE", override_url=c_url, override_key=c_key)
            print(f"[Supabase Clear All] Purged chat_history table. Status: {res.get('status')}")
            return self._send_json_response(res)

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def do_GET(self):
        """Handle page loads and API endpoints."""
        if self.path == "/api/status":
            cfg = get_supabase_config()
            data = {
                "status": "online",
                "institution_count": len(INSTITUTIONS),
                "system": "Gujarat Science Higher Education QA Engine",
                "supabase_configured": cfg["configured"]
            }
            return self._send_json_response(data)

        if self.path == "/api/colleges":
            data = {
                "total": len(INSTITUTIONS),
                "institutions": [
                    {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "city": c.get("city"),
                        "type": c.get("type"),
                        "category": c.get("category"),
                        "is_government": c.get("is_government")
                    }
                    for c in INSTITUTIONS
                ]
            }
            return self._send_json_response(data)

        # Supabase Config Status
        if self.path == "/api/supabase/config":
            cfg = get_supabase_config()
            masked_key = ""
            if cfg["key"]:
                masked_key = cfg["key"][:6] + "..." + cfg["key"][-4:] if len(cfg["key"]) > 10 else "***"
            return self._send_json_response({
                "configured": cfg["configured"],
                "supabase_url": cfg["url"],
                "masked_key": masked_key,
                "has_key": bool(cfg["key"])
            })

        # Fetch all Chat History from Supabase
        if self.path.startswith("/api/supabase/history"):
            res = supabase_api_request("chat_history?order=created_at.asc", method="GET")
            return self._send_json_response(res)

        # Map root to index.html with multi-path resolution
        if self.path in ["", "/", "/index.html"]:
            self.path = "/index.html"
            for candidate in [os.path.join(CURRENT_DIR, "index.html"), os.path.join(CURRENT_DIR, "static", "index.html")]:
                if os.path.isfile(candidate):
                    with open(candidate, "rb") as f:
                        content = f.read()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return

        # Direct asset resolution fallback (style.css, app.js, knowledge.js, etc.)
        clean_rel = self.path.split("?")[0].lstrip("/")
        if clean_rel:
            for base_dir in [CURRENT_DIR, os.path.join(CURRENT_DIR, "static")]:
                target_path = os.path.join(base_dir, clean_rel)
                if os.path.isfile(target_path):
                    content_type, _ = mimetypes.guess_type(target_path)
                    with open(target_path, "rb") as f:
                        content = f.read()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", content_type or "application/octet-stream")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return

        super().do_GET()

# ==============================================================================
# VERCEL SERVERLESS WSGI & HTTP APPLICATION
# ==============================================================================

def wsgi_application(environ, start_response):
    """Standard WSGI entrypoint for Vercel Python Runtime."""
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET").upper()

    cors_headers = [
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type, Authorization, apikey")
    ]

    if method == "OPTIONS":
        start_response("204 No Content", cors_headers)
        return [b""]

    # 1. Main Chat Endpoint
    if method == "POST" and path in ("/api/chat", "/api/chat/"):
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0))
            raw_body = environ["wsgi.input"].read(content_length) if content_length > 0 else b"{}"
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            payload = {}

        query = payload.get("query", "").strip()
        session_id = payload.get("session_id")
        session_title = payload.get("session_title")

        if not query:
            resp_data = {
                "status": "error",
                "answer": "Please ask a question regarding higher education after 12th Science in Gujarat."
            }
        else:
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

            resp_data = {
                "status": "success" if success else "error",
                "answer": answer,
                "created_at": created_at,
                "date_str": date_str,
                "supabase_saved": supabase_saved
            }

        out_bytes = json.dumps(resp_data, ensure_ascii=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(out_bytes)))
        ] + cors_headers
        start_response("200 OK", headers)
        return [out_bytes]

    # 2. Colleges & Health API
    if method == "GET" and path in ("/api/colleges", "/api/colleges/"):
        out_bytes = json.dumps({"count": len(INSTITUTIONS), "institutions": INSTITUTIONS}, ensure_ascii=False).encode("utf-8")
        headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(out_bytes)))] + cors_headers
        start_response("200 OK", headers)
        return [out_bytes]

    if method == "GET" and path in ("/api/health", "/api/health/"):
        out_bytes = json.dumps({"status": "online", "institution_count": len(INSTITUTIONS)}, ensure_ascii=False).encode("utf-8")
        headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(out_bytes)))] + cors_headers
        start_response("200 OK", headers)
        return [out_bytes]

    # 3. Serve Static Files (Homepage index.html, style.css, app.js, knowledge.js, etc.)
    target_rel = "index.html" if path in ("", "/", "/index", "/index.html") else path.lstrip("/")
    for base_dir in [CURRENT_DIR, os.path.join(CURRENT_DIR, "static")]:
        candidate = os.path.join(base_dir, target_rel)
        if os.path.isfile(candidate):
            content_type, _ = mimetypes.guess_type(candidate)
            if not content_type:
                content_type = "text/html" if candidate.endswith(".html") else "application/octet-stream"
            with open(candidate, "rb") as f:
                content = f.read()
            headers = [
                ("Content-Type", f"{content_type}; charset=utf-8" if "text" in content_type or "javascript" in content_type else content_type),
                ("Content-Length", str(len(content))),
                ("Cache-Control", "public, max-age=0, must-revalidate")
            ] + cors_headers
            start_response("200 OK", headers)
            return [content]

    # 4. Fallback 404
    not_found_body = b'{"error": "Not Found"}'
    headers = [("Content-Type", "application/json"), ("Content-Length", str(len(not_found_body)))] + cors_headers
    start_response("404 Not Found", headers)
    return [not_found_body]

# Export standard Vercel entrypoints
app = wsgi_application
application = wsgi_application
handler = wsgi_application




def run_server(port=8000, open_browser=False):
    ports_to_try = [port, 8080, 8081, 5000, 3000]
    httpd = None
    active_port = None

    for p in ports_to_try:
        try:
            server_address = ("127.0.0.1", p)
            httpd = ThreadingHTTPServer(server_address, GujaratEduHandler)
            active_port = p
            break
        except OSError:
            continue

    if not httpd:
        print("[Error] Could not bind to any test port.")
        sys.exit(1)

    url = f"http://localhost:{active_port}"
    cfg = get_supabase_config()
    db_status = "Connected" if cfg["configured"] else "Not configured (Local Fallback Mode)"

    print("=" * 68)
    print("  GujaratEdu Higher Education QA Bot: Web Frontend & Supabase Server")
    print(f"  Local Web UI URL: {url}")
    print(f"  Supabase DB Status: {db_status}")
    print(f"  Serving Static Assets From: {STATIC_DIR}")
    print("=" * 68)
    print("Press Ctrl + C to stop the server.\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[GujaratEdu Server] Shutting down gracefully...")
        httpd.shutdown()
        httpd.server_close()
        print("[GujaratEdu Server] Server stopped.")

if __name__ == "__main__":
    auto_open = "--open" in sys.argv
    requested_port = 8000
    for arg in sys.argv[1:]:
        if arg.isdigit():
            requested_port = int(arg)
            break
    run_server(port=requested_port, open_browser=auto_open)
