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
        [["x_studio_payg_event_id", "=", data["EventTS"]]],
        ["id"]
    ])

    if existing:
        dst_path = os.path.join(PROCESSED_DIR, clean_name)
        shutil.move(src_path, dst_path)
        return {"status": "duplicate", "message": "Event already exists"}

    # Create new event
    payload = {
        "x_studio_payg_event_id": data["EventTS"],
        "x_studio_event_timestamp_local": event_timestamp_local,
        "x_studio_schema_version": SCHEMA_VERSION,
    
        # Device metadata
        "x_studio_device_id": data["DeviceID"],
        "x_studio_device_ip": data["DeviceIP"],
        "x_studio_firmware_version": data["Firmware"],
    
        # Patient & physician
        "x_studio_patient_id_external": data["PatientID"],
        "x_studio_physician_id_external": data["PhysicianID"],
    
        # Raw payload
        "x_studio_payload_json": json.dumps(data),
    
        # Status
        "x_studio_status": "New",
    
        # Ingestion timestamp (optional but recommended)
        "x_studio_ingested_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
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
        while True:
            files = os.listdir(DEPOSIT_DIR)
    
            for filename in files:
                result = process_event_file(filename)
                print(result)
    
            time.sleep(1)

if __name__ == "__main__":
    main()
