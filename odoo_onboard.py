# --------------------------------------------------
# Odoo Onboarding Integration
# --------------------------------------------------

import json
import os
from datetime import datetime
from services.odoo_client import odoo

# --------------------------------------------------
# Load field mappings
# --------------------------------------------------

def load_field_map():
    with open("field_map.json", "r") as f:
        return json.load(f)

def build_odoo_values(data, field_map_categories=None):
    """
    1. Flattens field_map.json to map form_field -> odoo_field.
    2. Maps submitted form data to the Odoo record values dictionary.
    3. Identifies unexpected/unmapped keys and saves them to 'x_unmapped_fields'.
    4. Attaches the structured audit & report blueprint to 'x_json_payload'.
    """
    if field_map_categories is None:
        field_map_categories = load_field_map()

    # 1. Flatten the nested structure into a direct form_field -> odoo_field dictionary
    flat_map = {}
    for cat in field_map_categories:
        for fld in cat.get("fields", []):
            flat_map[fld["form_field"]] = fld["odoo_field"]
    
    # 2. Map known fields from incoming payload into Odoo values
    vals = {}
    for source_field, target_field in flat_map.items():
        if source_field in data:
            vals[target_field] = data[source_field]

    # --------------------------------------------------
    # Convert x_version string to Many2one integer ID
    # --------------------------------------------------
    version_val = vals.get("x_version")
    if version_val:
        # If it's already an integer (e.g. passed as ID), keep it
        if not isinstance(version_val, int):
            try:
                # Query x_payg_version to find the matching ID by string name
                matched = odoo.search_read(
                    "x_payg_version",
                    [("x_name", "=", str(version_val).strip())],
                    ["id"],
                    limit=1
                )
                vals["x_version"] = matched[0]["id"] if matched else False
            except Exception as e:
                # Log or fallback to False so Odoo doesn't throw InvalidTextRepresentation
                print(f"[ODOO ONBOARD] Failed to resolve version ID for '{version_val}': {e}")
                vals["x_version"] = False

    # 3. Find any fields in the incoming payload that are NOT in field_map.json
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
    vals["x_status"] = "received"

    # Clean up JSON file to remove signature image text
    # Create a copy so you don't affect other processes using data
    payload_to_save = data.copy()

    # Signature handling
    signature_image = data.get("signature_image")
    if signature_image:
        if "," in signature_image:
            signature_image = signature_image.split(",", 1)[1]
        vals["x_signature_image"] = signature_image
    
    # 5. Now dump to JSON / file
    vals["x_json_payload"] = build_report_layout_json(data, field_map_categories)
   
    return vals

def build_report_layout_json(data, field_map_categories=None):
    """
    Creates the dynamic audit trail & report blueprint JSON string.
    - Preserves submitted categories and fields.
    - Fields with sequences are pre-sorted (10, 20, 30...).
    - System / telemetry fields are retained with exclude_from_report: true.
    - Empty or unsubmitted fields are omitted.
    """
    report_layout = []

    for cat in field_map_categories:
        submitted_fields = []
        
        # Sort fields by sequence if available; fallback to natural order (999)
        sorted_fields = sorted(cat.get("fields", []), key=lambda x: x.get("sequence", 999))

        for fld in sorted_fields:
            form_key = fld["form_field"]
            odoo_key = fld.get("odoo_field", "")

            # If the field was not submitted (e.g. section omitted from form), skip it entirely!
            if form_key not in data:
                continue
    
            # Grab submitted value; if missing or None, default to ""
            val = data.get(form_key)
            if val is None:
                val = ""
                
            # Check if this is explicitly a filename field (always treated as normal string)
            is_filename_text = (
                "filename" in form_key.lower() 
                or "filename" in odoo_key.lower()
            )

            # Check if this field represents the actual binary upload
            is_binary_file = not is_filename_text and (
                fld.get("type") in ("binary", "file")
                or fld.get("is_file", False)
                or form_key.lower().endswith(("_pdf", "_file", "_doc", "_attachment"))
                or odoo_key.lower().endswith(("_pdf", "_file", "_doc", "_attachment"))
            )

            if is_binary_file:
                # Actual binary file: replace with comment or attached name
                if val:
                    filename = (
                        data.get(f"{form_key}_filename") 
                        or data.get(fld.get("filename_field", ""))
                        or data.get("x_submission_receipt_filename", "")
                    )
                    display_comment = f"[File Attached: {filename}]" if filename else "[File Attached]"
                else:
                    display_comment = ""

                field_entry = {
                    "odoo_field": odoo_key,
                    "is_file": True,
                    "filename_field": fld.get("filename_field"),
                    "value": display_comment
                }
            else:
                # Regular Char, Text, Number, Selection, or Filename String
                field_entry = {
                    "odoo_field": odoo_key,
                    "is_file": False,
                    "value": str(val).strip() if isinstance(val, str) else val
                }
                
            # Include label if defined
            if "label" in fld:
                field_entry["label"] = fld["label"]

            # Include sequence if defined
            if "sequence" in fld:
                field_entry["sequence"] = fld["sequence"]

            submitted_fields.append(field_entry)

        # Include category only if it has submitted fields
        if submitted_fields:
            report_layout.append({
                "category": cat["category"],
                "exclude_from_report": cat.get("exclude_from_report", False),
                "fields": submitted_fields
            })

    return json.dumps(report_layout, indent=2)

def process_submission_for_odoo(data):
    """
    Main helper function to call inside your endpoint/route handler.
    Returns the complete values dictionary ready to create/write in Odoo.
    """
    # Load mapping once for performance
    field_map_categories = load_field_map()

    # 1. Build standard Odoo table values
    vals = build_odoo_values(data, field_map_categories)

    # 2. Build the structured audit & report layout JSON
    # (Adjust 'x_report_layout_json' to match the exact field name on your Odoo model)
    vals["x_report_layout_json"] = build_report_layout_json(data, field_map_categories)

    return vals

# --------------------------------------------------
# Create onboarding record
# --------------------------------------------------

def create_onboarding_record(data):
    # 1. Map values using your existing business logic
    vals = build_odoo_values(data)

    # 2. Create the record in Odoo via the shared client
    record_id = odoo.create("x_payg_onboarding", vals)

    # 3. Create your local receipt file
    receipt_json = create_odoo_receipt(
        submission_reference=data["x_submit_reference"],
        odoo_record_id=record_id,
        status="success",
        response_data={"record_id": record_id}
    )

    # 4. Update the Odoo record with the receipt JSON
    odoo.write("x_payg_onboarding", record_id, {
        "x_odoo_receipt": receipt_json
    })

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
