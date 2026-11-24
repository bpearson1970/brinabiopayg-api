"""
odoo_client.py
Centralized Odoo XML-RPC connection manager.
"""

import os
import xmlrpc.client
from typing import Any, Dict, List, Optional

class OdooClient:
    def __init__(
        self,
        url: Optional[str] = None,
        db: Optional[str] = None,
        user: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        # Pulls from environment variables by default, or accepts explicit overrides
        self.url = (url or os.getenv("ODOO_URL", "")).rstrip("/")
        self.db = db or os.getenv("ODOO_DB", "")
        self.user = user or os.getenv("ODOO_USER", "odoo@brinamedical.com")
        self.api_key = api_key or os.getenv("ODOO_API_KEY", "")

        self._uid: Optional[int] = None
        self._common_proxy = None
        self._models_proxy = None

    @property
    def common(self):
        if not self._common_proxy:
            self._common_proxy = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/common"
            )
        return self._common_proxy

    @property
    def models(self):
        if not self._models_proxy:
            self._models_proxy = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/object"
            )
        return self._models_proxy

    def authenticate(self) -> int:
        """Authenticates with Odoo and caches the UID."""
        if self._uid is not None:
            return self._uid

        if not all([self.url, self.db, self.user, self.api_key]):
            raise ValueError(
                "Missing Odoo credentials. Ensure ODOO_URL, ODOO_DB, "
                "ODOO_USER, and ODOO_API_KEY are configured."
            )

        uid = self.common.authenticate(self.db, self.user, self.api_key, {})
        if not uid:
            raise PermissionError(
                f"Odoo authentication failed for user '{self.user}' on DB '{self.db}'."
            )

        self._uid = uid
        return self._uid

    def execute(self, model: str, method: str, *args, **kwargs) -> Any:
        """Generic execution wrapper for any Odoo model method."""
        uid = self.authenticate()
        return self.models.execute_kw(
            self.db, uid, self.api_key, model, method, list(args), kwargs
        )

    # --- Convenience Helpers ---

    def create(self, model: str, values: Dict[str, Any]) -> int:
        """Create a single record in the specified model and return its ID."""
        return self.execute(model, "create", [values])

    def write(self, model: str, record_id: int, values: Dict[str, Any]) -> bool:
        """Update a record by ID."""
        return self.execute(model, "write", [[record_id], values])

    def search_read(
        self,
        model: str,
        domain: Optional[List] = None,
        fields: Optional[List[str]] = None,
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        """Search and read records matching a domain."""
        return self.execute(
            model,
            "search_read",
            domain or [],
            {"fields": fields or [], "limit": limit},
        )


# Singleton instance ready to import directly
odoo = OdooClient()

