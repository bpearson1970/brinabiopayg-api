import os
import json
import requests
from datetime import datetime

ODOO_URL = "https://brina-medical-inc.odoo.com/jsonrpc"
ODOO_DB = "brina-medical-inc-odoo-com"  # check in Settings → Database name
ODOO_API_KEY = os.getenv("b9bb0be72ca6673c277f28e7edc75a6f2dc89d91")  # create in Odoo, use as password
ODOO_LOGIN = "brent@brinamedical.com"  # the user owning the API key

def odoo_jsonrpc(model, method, args=None, kwargs=None):
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                ODOO_DB,
                _get_uid(),
                ODOO_API_KEY,
                model,
                method,
                args or [],
                kwargs or {},
            ],
        },
        "id": 1,
    }
    r = requests.post(ODOO_URL, json=payload)
    r.raise_for_status()
    resp = r.json()
    if "error" in resp:
        raise Exception(resp["error"])
    return resp["result"]

_uid_cache = None
def _get_uid():
    global _uid_cache
    if _uid_cache is not None:
        return _uid_cache
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "common",
            "method": "authenticate",
            "args": [ODOO_DB, ODOO_LOGIN, ODOO_API_KEY, {}],
        },
        "id": 1,
    }
    r = requests.post(ODOO_URL, json=payload)
    r.raise_for_status()
    resp = r.json()
    if "error" in resp or resp.get("result") is False:
        raise Exception("Authentication failed")
    _uid_cache = resp["result"]
    return _uid_cache
