import os
import json
import shutil
from datetime import datetime
from odoo_rpc import odoo_jsonrpc

DEPOSIT_DIR = "/var/data/event_deposit"
PROCESSED_DIR = "/var/data/event_processed"
ERROR_DIR = "/var/data/event_error"

# Ensure directories exist
os.makedirs(DEPOSIT_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(ERROR_DIR, exist_ok=True)

def ingest_event_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    required = ["DeviceID", "DeviceIP", "Firmware", "EventTS", "PatientID", "PhysicianID"]
    missing = [k for k in required if k not in data]
    if missing:
        return {"status": "error", "message": f"Missing fields: {missing}"}

    event_ts = data["EventTS"]
    external_event_id = event_ts

    try:
        ts_raw = event_ts.split("_")[0]
        event_timestamp_local = datetime.strptime(ts_raw, "%Y%m%dT%H%M%S")
    except Exception as e:
        return {"status": "error", "message": f"Invalid EventTS format: {e}"}

    # Duplicate check
    existing = odoo_jsonrpc(
        "x_payg_event",
        "search_read",
        args=[[("external_event_id", "=", external_event_id)]],
        kwargs={"fields": ["id", "status"], "limit": 1},
    )

    if existing:
        odoo_jsonrpc(
            "x_payg_event",
            "write",
            args=[[existing[0]["id"]], {"status": "duplicate"}],
        )
        return {"status": "duplicate", "record_id": existing[0]["id"]}

    vals = {
        "external_event_id": external_event_id,
        "event_timestamp_local": event_timestamp_local.strftime("%Y-%m-%d %H:%M:%S"),
        "device_id": data["DeviceID"],
        "device_ip": data["DeviceIP"],
        "firmware_version": data["Firmware"],
        "patient_id_external": data["PatientID"],
        "physician_id_external": data["PhysicianID"],
        "payload_json": json.dumps(data),
        "schema_version": os.getenv("SCHEMA_VERSION","1.0"),
        "status": "new",
        "ingested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    record_id = odoo_jsonrpc("x_payg_event", "create", args=[vals])
    return {"status": "success", "record_id": record_id}

def process_all():
    for fname in os.listdir(DEPOSIT_DIR):
        if not fname.endswith(".json"):
            continue

        src = os.path.join(DEPOSIT_DIR, fname)
        result = ingest_event_file(src)

        if result["status"] in ("success", "duplicate"):
            shutil.move(src, os.path.join(PROCESSED_DIR, fname))
        else:
            shutil.move(src, os.path.join(ERROR_DIR, fname))

if __name__ == "__main__":
    process_all()
