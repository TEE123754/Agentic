"""A loopback-only, bounded client for the dashboard's read/write API."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx


class DashboardAPIError(RuntimeError):
    pass


class DashboardClient:
    def __init__(self, base_url="http://127.0.0.1:8765"):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.port is None
        ):
            raise ValueError("Dashboard API must be an explicit 127.0.0.1 HTTP endpoint")
        self.base_url = f"http://127.0.0.1:{parsed.port}"
        self.http = httpx.Client(
            base_url=self.base_url, timeout=8, trust_env=False, follow_redirects=False
        )

    def close(self):
        self.http.close()

    def _request(self, method, path, **kwargs):
        if not path.startswith("/") or path.startswith("//") or "://" in path:
            raise ValueError("Dashboard API path must be local and relative")
        try:
            response = self.http.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            raise DashboardAPIError(
                "Local cohort API is unavailable. Start `python -m frictionlab serve`."
            ) from exc
        if response.status_code >= 400:
            try:
                payload = response.json()
                detail = payload.get("detail") or payload.get("report", {}).get("terminal_reason")
            except (ValueError, AttributeError):
                detail = None
            raise DashboardAPIError(
                str(detail or f"Local API returned HTTP {response.status_code}")[:300]
            )
        if len(response.content) > 20 * 1024 * 1024:
            raise DashboardAPIError("Requested local artifact exceeds the dashboard size ceiling")
        return response

    def get(self, path):
        return self._request("GET", path).json()

    def get_optional(self, path):
        try:
            return self.get(path)
        except DashboardAPIError as exc:
            if "HTTP 404" in str(exc) or "Report does not exist" in str(exc):
                return None
            raise

    def bytes(self, path):
        return self._request("GET", path).content

    def post(self, path, payload=None):
        return self._request("POST", path, json=payload).json()
