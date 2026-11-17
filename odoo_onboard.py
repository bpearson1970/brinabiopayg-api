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

def get_flat_field_map():
    """Flattens the nested category structure into a simple source -> target dictionary."""
    categories = load_field_map()
    flat_map = {}
    
    for category in categories:
        for fld in category.get("fields", []):
            flat_map[fld["form_field"]] = fld["odoo_field"]
            
    return flat_map
    
# --------------------------------------------------
# Build Odoo values dictionary
# --------------------------------------------------

def build_odoo_values(data):
    flat_map = get_flat_field_map()
    vals = {}

    # 1. Map existing fields into Odoo field name
    for source_field, target_field in flat_map.items():

        if source_field in data:
            vals[target_field] = data[source_field]

    # 2. Find any fields in the incoming payload that are NOT in field_map.json
        incoming_keys = set(data.keys())
        mapped_keys = set(flat_map.keys())
        unmapped = incoming_keys - mapped_keys
        
        # Exclude fields handled separately
        unmapped.discard("signature_image")

    # 3. Send unmapped fields to Odoo field as JSON
    if unmapped:
        # Collects the field names AND their entered values:
        unmapped_data = {k: data[k] for k in unmapped}
        vals["x_unmapped_fields"] = json.dumps(unmapped_data, indent=2)
    else:
        vals["x_unmapped_fields"] = False

    # 4. System-managed fields
    vals["x_status"] = "Received"

    # Clean up JSON file to remove signature image text
    # Create a copy so you don't affect other processes using data
    payload_to_save = data.copy()

    if "signature_image" in payload_to_save:
        payload_to_save["signature_image"] = "[SIGNATURE_IMAGE_ATTACHED_SEPARATELY]"

    # Now dump to JSON / file
    vals["x_json_payload"]  = json.dumps(payload_to_save, indent=2)

    signature_image = data.get("signature_image")
    
    if signature_image:

        if "," in signature_image:
            signature_image = signature_image.split(",", 1)[1]

        vals["x_signature_image"] = signature_image
    
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

    receipt_json = json.dumps(receipt, indent=4)

    with open(receipt_file, "w", encoding="utf-8") as file:
        file.write(receipt_json)

    return receipt_json
