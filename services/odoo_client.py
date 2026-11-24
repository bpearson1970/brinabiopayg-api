"""
odoo_client.py
Centralized Odoo JSON-RPC client preserving your exact environment variable conventions.
"""

import os
import requests
from typing import Any, Dict, List, Optional


class OdooClient:
    def __init__(
        self,
        url: Optional[str] = None,
        db: Optional[str] = None,
        login: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        # Match your exact environment variable names
        raw_url = url or os.getenv("ODOO_URL", "")
        # Ensure the URL points to the JSON-RPC endpoint
        if raw_url and not raw_url.endswith("/jsonrpc"):
            raw_url = raw_url.rstrip("/") + "/jsonrpc"
        self.url = raw_url

        self.db = db or os.getenv("ODOO_DB", "")
        self.login = login or os.getenv("ODOO_LOGIN", "odoo@brinamedical.com")
        self.api_key = api_key or os.getenv("ODOO_API_KEY", "")

        self._uid: Optional[int] = None
        self._request_id: int = 1

    def _call(self, service: str, method: str, *args) -> Any:
        """Low-level JSON-RPC transport wrapper."""
        if not all([self.url, self.db, self.login, self.api_key]):
            raise ValueError(
                "Missing Odoo configuration. Verify ODOO_URL, ODOO_DB, "
                "ODOO_LOGIN, and ODOO_API_KEY are set."
            )

        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": service,
                "method": method,
                "args": list(args),
            },
            "id": self._request_id,
        }
        self._request_id += 1

        response = requests.post(self.url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise Exception(f"Odoo JSON-RPC Error: {data['error']}")
        if "result" not in data:
            raise Exception(f"Malformed Odoo response: {data}")

        return data["result"]

    def authenticate(self) -> int:
        """Preserves your existing authenticate_odoo logic and caches the UID."""
        if self._uid is not None:
            return self._uid

        uid = self._call(
            "common",
            "authenticate",
            self.db,
            self.login,
            self.api_key,
            {},
        )

        if not uid:
            raise PermissionError(
                f"Odoo authentication failed for login '{self.login}' on DB '{self.db}'."
            )

        self._uid = uid
        return self._uid

    def execute_kw(self, model: str, method: str, args: List[Any], kwargs: Optional[Dict[str, Any]] = None) -> Any:
        """Calls object execute_kw through the jsonrpc endpoint."""
        uid = self.authenticate()
        return self._call(
            "object",
            "execute_kw",
            self.db,
            uid,
            self.api_key,
            model,
            method,
            args,
            kwargs or {},
        )

    # --- High-level CRUD operations ---

    def create(self, model: str, values: Dict[str, Any]) -> int:
        """Create a record and return its new ID."""
        return self.execute_kw(model, "create", [values])

    def write(self, model: str, record_id: int, values: Dict[str, Any]) -> bool:
        """Update a record by ID."""
        return self.execute_kw(model, "write", [[record_id], values])

    def search_read(
        self,
        model: str,
        domain: Optional[List] = None,
        fields: Optional[List[str]] = None,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Search and read matching records."""
        return self.execute_kw(
            model,
            "search_read",
            [domain or []],
            {"fields": fields or [], "limit": limit},
        )


# Global singleton instance
odoo = OdooClient()
