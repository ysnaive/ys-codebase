"""
OAuth 2.0 Client ID configuration loading, authorization URL construction,
code extraction, token exchange, and localhost loopback server flow.
"""
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, Tuple
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from core import vfs
from core.log import log

from .config import GDriveConfigError, GDriveTransportError

OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_DEFAULT_SCOPE = "https://www.googleapis.com/auth/drive"


def load_oauth_client_config(cred_path: Path) -> Tuple[str, str]:
    """
    Parse Google OAuth 2.0 Client ID JSON ('installed' or 'web' format) and return (client_id, client_secret).
    """
    if not cred_path.is_file():
        raise GDriveConfigError(
            f"OAuth2 client credentials file not found at '{cred_path.as_posix()}'.\n"
            "Please place your downloaded Google Cloud OAuth 2.0 Client ID JSON at this path."
        )
    try:
        raw = json.loads(cred_path.read_text(encoding="utf-8"))
        try:
            os.chmod(cred_path, 0o600)
        except OSError:
            pass
    except Exception as exc:
        raise GDriveConfigError(
            f"Invalid JSON in '{cred_path.as_posix()}': {exc}"
        ) from exc

    block = raw.get("installed") or raw.get("web") or raw
    if not isinstance(block, dict):
        raise GDriveConfigError(
            f"Unrecognized OAuth2 client credentials structure in '{cred_path.as_posix()}'."
        )
    client_id = str(block.get("client_id") or "").strip()
    client_secret = str(block.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise GDriveConfigError(
            f"Missing 'client_id' or 'client_secret' in '{cred_path.as_posix()}'."
        )
    return client_id, client_secret


def build_oauth_authorize_url(
    client_id: str,
    redirect_uri: str,
    scope: str = DRIVE_DEFAULT_SCOPE,
    state: str = "",
) -> str:
    """Build the Google OAuth 2.0 authorization URL for offline refresh_token access."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
    }
    if state:
        params["state"] = state
    return f"{OAUTH_AUTH_URL}?{urllib.parse.urlencode(params)}"


def extract_code_from_input(raw_code_or_url: str) -> str:
    """
    Accept either a raw authorization code or a full redirect URL (e.g. http://127.0.0.1:8080/?code=4/0A...&scope=...)
    and extract the 'code' value.
    """
    val = raw_code_or_url.strip()
    if val.startswith(("http://", "https://", "localhost", "127.0.0.1")) or "?code=" in val or "&code=" in val:
        parsed = urllib.parse.urlparse(val if "://" in val else f"http://{val}")
        qs = urllib.parse.parse_qs(parsed.query)
        codes = qs.get("code") or []
        if codes:
            return str(codes[0]).strip()
    return val


def exchange_oauth_code_for_token(
    client_id: str,
    client_secret: str,
    code_or_url: str,
    redirect_uri: str,
    token_path: Path,
) -> Dict[str, Any]:
    """
    Exchange an OAuth2 authorization code for access_token + refresh_token and persist atomically to token_path.
    """
    code = extract_code_from_input(code_or_url)
    if not code:
        raise GDriveTransportError("Authorization code is empty.")

    payload = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            token_resp = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        finally:
            try:
                exc.close()
            except Exception:
                pass
        raise GDriveTransportError(
            f"OAuth2 token exchange failed (HTTP {exc.code}): {err_body}"
        ) from exc
    except Exception as exc:
        raise GDriveTransportError(f"OAuth2 token exchange failed: {exc}") from exc

    existing_refresh = ""
    if token_path.is_file():
        try:
            old_data = json.loads(token_path.read_text(encoding="utf-8"))
            existing_refresh = str(old_data.get("refresh_token") or "")
        except (OSError, ValueError):
            existing_refresh = ""

    expires_in = float(token_resp.get("expires_in", 3600))
    stored_token: Dict[str, Any] = {
        "access_token": str(token_resp["access_token"]),
        "refresh_token": str(token_resp.get("refresh_token") or existing_refresh),
        "token_type": str(token_resp.get("token_type", "Bearer")),
        "scope": str(token_resp.get("scope", DRIVE_DEFAULT_SCOPE)),
        "expiry_epoch": time.time() + expires_in,
        "client_id": client_id,
    }
    token_path.parent.mkdir(parents=True, exist_ok=True)
    vfs.write_json(token_path, stored_token, indent=2, encoding="utf-8", atomic=True)
    try:
        os.chmod(token_path, 0o600)
    except OSError:
        pass
    return stored_token


def run_oauth_loopback_flow(
    cred_path: Path,
    token_path: Path,
    port: int = 0,
    open_browser: bool = True,
    timeout_sec: float = 180.0,
) -> Dict[str, Any]:
    """
    Start a temporary localhost HTTP loopback listener on 127.0.0.1:<port>, print the Google OAuth2
    consent URL, and wait for the browser redirect (or allow fallback via --code).
    """
    client_id, client_secret = load_oauth_client_config(cred_path)
    captured: Dict[str, str] = {}

    class _OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if "code" in qs and qs["code"]:
                captured["code"] = qs["code"][0]
                body = (
                    "<html><body style='font-family:sans-serif;padding:2rem;'>"
                    "<h2>YS-Codebase Google Drive Authorization Successful</h2>"
                    "<p>You may close this tab and return to your terminal.</p>"
                    "</body></html>"
                ).encode("utf-8")
                self.send_response(200)
            else:
                err = (qs.get("error") or ["unknown_error"])[0]
                captured["error"] = err
                safe_err = html.escape(str(err))
                body = (
                    f"<html><body><h2>Authorization Failed: {safe_err}</h2></body></html>"
                ).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", port), _OAuthCallbackHandler)
    actual_port = server.server_port
    redirect_uri = f"http://127.0.0.1:{actual_port}"
    auth_url = build_oauth_authorize_url(client_id, redirect_uri)

    log(
        f"\n[gdrive-support:auth] Open the following URL in your browser to authorize:\n\n  {auth_url}\n",
        stream="stderr",
    )
    log(
        f"[gdrive-support:auth] Listening on {redirect_uri} (timeout={int(timeout_sec)}s)...\n"
        f"  (Tip: In a headless container, if your browser redirects to {redirect_uri}/?code=... and cannot connect,\n"
        f"   copy that full URL or the 'code' parameter and run:\n"
        f"   python yscb.py gdrive auth --code=\"<CODE_OR_REDIRECT_URL>\" --port={actual_port})\n",
        stream="stderr",
        flush=True,
    )
    if open_browser:
        try:
            webbrowser.open(auth_url)
        except (OSError, webbrowser.Error):
            pass

    server.timeout = 1.0
    deadline = time.time() + timeout_sec
    try:
        while time.time() < deadline and "code" not in captured and "error" not in captured:
            server.handle_request()
    finally:
        server.server_close()

    if "error" in captured:
        raise GDriveTransportError(f"OAuth2 authorization denied: {captured['error']}")
    if "code" not in captured:
        raise GDriveTransportError(
            "Timed out waiting for OAuth2 callback on loopback server."
        )

    return exchange_oauth_code_for_token(
        client_id=client_id,
        client_secret=client_secret,
        code_or_url=captured["code"],
        redirect_uri=redirect_uri,
        token_path=token_path,
    )
