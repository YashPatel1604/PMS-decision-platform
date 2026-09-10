"""Microsoft Graph: device-code auth + OneDrive read/write (personal accounts)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from pms_platform.config import settings

GRAPH_SCOPE = "https://graph.microsoft.com/Files.ReadWrite offline_access"


class OneDriveGraphError(RuntimeError):
    """Graph auth or file API failure."""


def _tenant() -> str:
    return (settings.microsoft_tenant_id or "consumers").strip() or "consumers"


def _token_url() -> str:
    return f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/token"


def _device_code_url() -> str:
    return f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/devicecode"


def credentials_configured() -> bool:
    return bool(settings.microsoft_client_id.strip() and settings.microsoft_refresh_token.strip())


def access_token_from_refresh(*, client: httpx.Client | None = None) -> str:
    if not credentials_configured():
        raise OneDriveGraphError(
            "Set MICROSOFT_CLIENT_ID and MICROSOFT_REFRESH_TOKEN (run: pms-platform onedrive-auth)"
        )
    data = {
        "client_id": settings.microsoft_client_id.strip(),
        "grant_type": "refresh_token",
        "refresh_token": settings.microsoft_refresh_token.strip(),
        "scope": GRAPH_SCOPE,
    }
    secret = settings.microsoft_client_secret.strip()
    if secret:
        data["client_secret"] = secret

    own = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        response = http.post(_token_url(), data=data)
        if response.is_error:
            raise OneDriveGraphError(
                f"token refresh {response.status_code}: {response.text[:400]}"
            )
        token = response.json().get("access_token")
        if not token:
            raise OneDriveGraphError("token refresh returned no access_token")
        return str(token)
    finally:
        if own:
            http.close()


def _authorize_url() -> str:
    return f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/authorize"


# Registered in Azure → Authentication → Mobile and desktop / Web.
LOCAL_REDIRECT_URI = "http://localhost:8765/callback"


def authorization_url(*, redirect_uri: str = LOCAL_REDIRECT_URI) -> str:
    from urllib.parse import urlencode

    client_id = settings.microsoft_client_id.strip()
    if not client_id:
        raise OneDriveGraphError("Set MICROSOFT_CLIENT_ID in .env first")
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": GRAPH_SCOPE,
    }
    return f"{_authorize_url()}?{urlencode(params)}"


def exchange_auth_code(
    code: str,
    *,
    redirect_uri: str = LOCAL_REDIRECT_URI,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Exchange authorization code for tokens (incl. refresh_token)."""
    client_id = settings.microsoft_client_id.strip()
    data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": GRAPH_SCOPE,
    }
    secret = settings.microsoft_client_secret.strip()
    if secret:
        data["client_secret"] = secret

    own = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        response = http.post(_token_url(), data=data)
        if response.is_error:
            raise OneDriveGraphError(
                f"code exchange {response.status_code}: {response.text[:400]}"
            )
        body = dict(response.json())
        if not body.get("refresh_token"):
            raise OneDriveGraphError("no refresh_token — check offline_access permission")
        return body
    finally:
        if own:
            http.close()


def run_localhost_auth(*, port: int = 8765, timeout_seconds: float = 300.0) -> dict[str, Any]:
    """Open browser auth; catch redirect on localhost; return token response."""
    import threading
    import time
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    redirect_uri = f"http://localhost:{port}/callback"
    url = authorization_url(redirect_uri=redirect_uri)
    result: dict[str, Any] = {}
    error: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            qs = parse_qs(parsed.query)
            if qs.get("error"):
                error.append(qs.get("error_description", qs["error"])[0])
                body = b"<html><body>Auth failed - close this tab.</body></html>"
            else:
                codes = qs.get("code") or []
                if not codes:
                    error.append("missing code in redirect")
                    body = b"<html><body>Missing code - close this tab.</body></html>"
                else:
                    result["code"] = codes[0]
                    body = b"<html><body>OK - you can close this tab and return to the terminal.</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    print(f"Opening browser for Microsoft login…\n{url}", flush=True)
    webbrowser.open(url)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline and not result and not error:
        time.sleep(0.2)
    server.server_close()
    if error:
        raise OneDriveGraphError(error[0])
    if not result.get("code"):
        raise OneDriveGraphError("auth timed out — no redirect received")
    return exchange_auth_code(str(result["code"]), redirect_uri=redirect_uri)


def start_device_code_flow(*, client: httpx.Client | None = None) -> dict[str, Any]:
    client_id = settings.microsoft_client_id.strip()
    if not client_id:
        raise OneDriveGraphError("Set MICROSOFT_CLIENT_ID in .env first")
    own = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        response = http.post(
            _device_code_url(),
            data={"client_id": client_id, "scope": GRAPH_SCOPE},
        )
        if response.is_error:
            raise OneDriveGraphError(
                f"device code {response.status_code}: {response.text[:400]}"
            )
        return dict(response.json())
    finally:
        if own:
            http.close()


def poll_device_code(
    device_code: str,
    *,
    interval_seconds: float = 5.0,
    max_attempts: int = 60,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    import time

    client_id = settings.microsoft_client_id.strip()
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": client_id,
        "device_code": device_code,
    }
    secret = settings.microsoft_client_secret.strip()
    if secret:
        data["client_secret"] = secret

    own = client is None
    http = client or httpx.Client(timeout=60.0)
    try:
        for _ in range(max_attempts):
            response = http.post(_token_url(), data=data)
            body = response.json()
            if response.is_success and body.get("refresh_token"):
                return dict(body)
            err = str(body.get("error") or "")
            if err in {"authorization_pending", "slow_down"}:
                wait = float(body.get("interval") or interval_seconds)
                if err == "slow_down":
                    wait += 5.0
                time.sleep(wait)
                continue
            raise OneDriveGraphError(
                f"device poll {response.status_code}: {response.text[:400]}"
            )
        raise OneDriveGraphError("device code timed out — run onedrive-auth again")
    finally:
        if own:
            http.close()


def get_drive_file(relative_path: str, *, access_token: str, client: httpx.Client | None = None) -> bytes:
    """Download a file under the signed-in user's OneDrive root."""
    rel = relative_path.lstrip("/").replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        raise OneDriveGraphError(f"invalid OneDrive path: {relative_path!r}")
    encoded = quote(rel, safe="/")
    url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded}:/content"
    own = client is None
    http = client or httpx.Client(timeout=300.0)
    try:
        response = http.get(url, headers={"Authorization": f"Bearer {access_token}"})
        if response.is_error:
            raise OneDriveGraphError(f"download {response.status_code}: {response.text[:400]}")
        return response.content
    finally:
        if own:
            http.close()


def put_drive_file(
    relative_path: str,
    data: bytes,
    *,
    access_token: str,
    client: httpx.Client | None = None,
) -> None:
    """Overwrite (or create) a file under the signed-in user's OneDrive root."""
    rel = relative_path.lstrip("/").replace("\\", "/")
    if not rel or ".." in rel.split("/"):
        raise OneDriveGraphError(f"invalid OneDrive path: {relative_path!r}")
    encoded = quote(rel, safe="/")
    session_url = f"https://graph.microsoft.com/v1.0/me/drive/root:/{encoded}:/createUploadSession"
    headers = {"Authorization": f"Bearer {access_token}"}
    own = client is None
    http = client or httpx.Client(timeout=300.0)
    try:
        created = http.post(
            session_url,
            headers=headers,
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        )
        if created.is_error:
            raise OneDriveGraphError(
                f"createUploadSession {created.status_code}: {created.text[:400]}"
            )
        upload_url = created.json().get("uploadUrl")
        if not upload_url:
            raise OneDriveGraphError("createUploadSession missing uploadUrl")
        size = len(data)
        put = http.put(
            upload_url,
            content=data,
            headers={
                "Content-Length": str(size),
                "Content-Range": f"bytes 0-{size - 1}/{size}",
            },
        )
        if put.is_error:
            raise OneDriveGraphError(f"upload {put.status_code}: {put.text[:400]}")
    finally:
        if own:
            http.close()
