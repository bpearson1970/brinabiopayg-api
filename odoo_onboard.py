# --------------------------------------------------
# Odoo Onboarding Integration
# --------------------------------------------------

import os
import json
import requests
from datetime import datetime

# --------------------------------------------------
# Authenticate to Odoo
# --------------------------------------------------

def authenticate_odoo():

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "common",
            "method": "authenticate",
            "args": [
                os.getenv("ODOO_DB"),
                os.getenv("ODOO_LOGIN"),
                os.getenv("ODOO_API_KEY"),
                {}
            ]
        },
        "id": 1
    }

    response = requests.post(
        os.getenv("ODOO_URL"),
        json=payload
    )

    result = response.json()

    if "result" not in result:
        raise Exception(
            f"Odoo authentication failed: {result}"
        )

    return result["result"]


# --------------------------------------------------
# Load field mappings
# --------------------------------------------------

def load_field_map():

    with open("field_map.json", "r") as f:
        return json.load(f)


# --------------------------------------------------
# Build Odoo values dictionary
# --------------------------------------------------

def build_odoo_values(data):

    field_map = load_field_map()

    vals = {}

    for source_field, target_field in field_map.items():

        if source_field in data:
            vals[target_field] = data[source_field]

    # System-managed fields

    vals["x_status"] = "Received"

    vals["x_json_payload"] = json.dumps(
        data,
        indent=2
    )

    return vals


# --------------------------------------------------
# Create onboarding record
# --------------------------------------------------

def create_onboarding_record(data):

    uid = authenticate_odoo()

    vals = build_odoo_values(data)

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.getenv("ODOO_DB"),
                uid,
                os.getenv("ODOO_API_KEY"),
                "x_payg_onboarding",
                "create",
                [vals]
            ]
        },
        "id": 2
    }

    response = requests.post(
        os.getenv("ODOO_URL"),
        json=payload
    )

    result = response.json()

    if "result" not in result:
        raise Exception(
            f"Odoo record creation failed: {result}"
        )

    record_id = result["result"]

    receipt_json = create_odoo_receipt(
        submission_reference=data["x_submit_reference"],
        odoo_record_id=record_id,
        status="success",
        response_data=result
    )

    write_payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.getenv("ODOO_DB"),
                uid,
                os.getenv("ODOO_API_KEY"),
                "x_payg_onboarding",
                "write",
                [
                    [record_id],
                    {
                        "x_odoo_receipt": receipt_json
                    }
                ]
            ]
        },
        "id": 3
    }

    response = requests.post(
        os.getenv("ODOO_URL"),
        json=write_payload
    )

    result = response.json()

    if "result" not in result:
        raise Exception(
            f"Odoo receipt update failed: {result}"
        )

    return record_id

def create_odoo_receipt(
    submission_reference,
    odoo_record_id,
    status,
    response_data
):

    receipt = {
        "submission_reference": submission_reference,
        "odoo_record_id": odoo_record_id,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "response": response_data
    }

    receipt_file = (
        f"/var/data/onboard/odoo_receipts/"
        f"{submission_reference}.receipt.json"
    )

    with open(
        receipt_file, "w", encoding="utf-8") as file:
        json.dump(receipt, file, indent=4)

    return receipt_file
