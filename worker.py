import os
import json
import shutil
from datetime import datetime
from odoo_rpc import odoo_jsonrpc

DEPOSIT_DIR = "/var/data/event_deposit"
PROCESSED_DIR = "/var/data/event_processed"
ERROR_DIR = "/var/data/event_error"

SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "1.0")


def sanitize_filename(name: str) -> str:
    """
    Remove hidden characters such as CR, LF, tabs, nulls, and non‑printable ASCII.
    This prevents ingestion failures caused by Windows CRLF or device‑generated strings.
    """
    return "".join(c for c in name if c.isprintable()).strip()


def load_json_file(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}


def process_event_file(filename: str):
    clean_name = sanitize_filename(filename)

    if not clean_name.endswith(".tmp"):
        return {"status": "skip", "message": "Not a .tmp file"}

    src_path = os.path.join(DEPOSIT_DIR, clean_name)
    data = load_json_file(src_path)

    if "status" in data and data["status"] == "error":
        dst_path = os.path.join(ERROR_DIR, clean_name)
        shutil.move(src_path, dst_path)
        return {"status": "error", "message": data["message"]}

    # Required fields
    required = ["DeviceID", "DeviceIP", "Firmware", "EventTS", "PatientID", "PhysicianID"]
    for field in required:
        if field not in data:
            dst_path = os.path.join(ERROR_DIR, clean_name)
            shutil.move(src_path, dst_path)
            return {"status": "error", "message": f"Missing field: {field}"}

    # Parse timestamp
    try:
        event_ts = data["EventTS"]
        event_dt = datetime.strptime(event_ts.split("_")[0], "%Y%m%dT%H%M%S")
        event_timestamp_local = event_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        dst_path = os.path.join(ERROR_DIR, clean_name)
        shutil.move(src_path, dst_path)
        return {"status": "error", "message": f"Timestamp parse error: {e}"}

    # Check duplicate
    existing = odoo_jsonrpc("x_payg_event", "search_read", [
        [["external_event_id", "=", data["EventTS"]]],
        ["id"]
    ])

    if existing:
        dst_path = os.path.join(PROCESSED_DIR, clean_name)
        shutil.move(src_path, dst_path)
        return {"status": "duplicate", "message": "Event already exists"}

    # Create new event
    payload = {
        "external_event_id": data["EventTS"],
        "event_timestamp_local": event_timestamp_local,
        "schema_version": SCHEMA_VERSION,
        "device_id": data["DeviceID"],
        "patient_id_external": data["PatientID"],
        "physician_id_external": data["PhysicianID"],
        "payload_json": json.dumps(data),
        "status": "new",
    }

    try:
        odoo_jsonrpc("x_payg_event", "create", [payload])
    except Exception as e:
        dst_path = os.path.join(ERROR_DIR, clean_name)
        shutil.move(src_path, dst_path)
        return {"status": "error", "message": f"Odoo create error: {e}"}

    dst_path = os.path.join(PROCESSED_DIR, clean_name)
    shutil.move(src_path, dst_path)
    return {"status": "ok", "message": "Event created"}


def main():
    for filename in os.listdir(DEPOSIT_DIR):
        result = process_event_file(filename)
        print(f"{filename}: {result}")


if __name__ == "__main__":
    main()
