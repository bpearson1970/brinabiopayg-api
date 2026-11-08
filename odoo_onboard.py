def create_onboarding_record(data):

    uid = authenticate_odoo()

    with open("field_map.json", "r") as f:
        field_map = json.load(f)

    vals = {}

    for source_field, target_field in field_map.items():

        if source_field in data:
            vals[target_field] = data[source_field]

    vals["x_status"] = "Received"

    vals["x_json_payload"] = json.dumps(
        data,
        indent=2
    )
