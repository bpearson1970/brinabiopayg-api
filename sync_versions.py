"""
sync_versions.py
Synchronizes version.json into Odoo x_payg_version.

Logic:
1. Queries Odoo for the latest 100 versions (order="id desc").
2. Examines the last 100 entries in version.json.
3. Finds the latest Odoo version in version.json.
4. Adds all subsequent versions from version.json to Odoo.
5. Handles empty Odoo tables automatically (seeds all entries).
"""

import json
import os
import subprocess
from datetime import datetime
from services.odoo_client import odoo


def detect_git_hash(version_str: str) -> str:
    """Detects Git commit hash from git history, HEAD, or Render environment."""
    # 1. Search git log for when this version was added in version.json
    try:
        commit_hash = (
            subprocess.check_output(
                ["git", "log", f"-S{version_str}", "-n", "1", "--pretty=format:%h", "version.json"],
                stderr=subprocess.DEVNULL,
            )
            .decode("ascii")
            .strip()
        )
        if commit_hash:
            return commit_hash
    except Exception:
        pass

    # 2. Search git HEAD
    try:
        commit_hash = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode("ascii")
            .strip()
        )
        if commit_hash:
            return commit_hash
    except Exception:
        pass

    # 3. Fallback to platform environment variable (e.g. Render)
    env_hash = os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or ""
    return env_hash[:7] if env_hash else "manual"


def parse_date_to_odoo(date_str: str) -> str:
    """Parses various date string formats and returns YYYY-MM-DD for Odoo."""
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.utcnow().strftime("%Y-%m-%d")


def sync_versions_to_odoo(json_file_path: str = "version.json"):
    if not os.path.exists(json_file_path):
        print(f"[VERSION SYNC] '{json_file_path}' not found. Skipping.")
        return

    with open(json_file_path, "r", encoding="utf-8") as f:
        try:
            all_json_versions = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[VERSION SYNC] Error parsing {json_file_path}: {e}")
            return

    if not isinstance(all_json_versions, list) or not all_json_versions:
        print(f"[VERSION SYNC] {json_file_path} is empty or not an array.")
        return

    print(f"[VERSION SYNC] Connecting to Odoo DB '{odoo.db}'...")

    # Step 1: Get the 100 most recent versions from Odoo
    odoo_records = odoo.search_read(
        "x_payg_version",
        domain=[],
        fields=["x_name"],
        order="id desc",
        limit=100,
    )

    # Step 2: Get the 100 most recent versions from JSON
    recent_json_versions = all_json_versions[-100:]

    versions_to_add = []

    # Step 3 & Exception handling for empty Odoo table
    if not odoo_records:
        # Case A: Odoo table is empty -> seed all recent versions from JSON
        print("[VERSION SYNC] Odoo 'x_payg_version' is empty. Initializing all versions.")
        versions_to_add = recent_json_versions
    else:
        # Case B: Odoo has records -> find latest Odoo version in the JSON list
        latest_odoo_version = odoo_records[0]["x_name"]
        print(f"[VERSION SYNC] Latest version in Odoo is '{latest_odoo_version}'.")

        # Find the index of this version in our JSON slice
        matched_index = None
        for i, entry in enumerate(recent_json_versions):
            if str(entry.get("version", "")).strip() == latest_odoo_version:
                matched_index = i
                break

        if matched_index is not None:
            # Everything in JSON AFTER this index needs to be added
            versions_to_add = recent_json_versions[matched_index + 1:]
        else:
            # Safety fallback: If latest Odoo version wasn't found in the JSON slice,
            # filter against all known recent Odoo names to avoid duplicate errors
            known_odoo_names = {rec["x_name"] for rec in odoo_records if rec.get("x_name")}
            versions_to_add = [
                entry for entry in recent_json_versions
                if str(entry.get("version", "")).strip() not in known_odoo_names
            ]

    # Step 4: Add missing versions to Odoo
    if not versions_to_add:
        print("[VERSION SYNC] Odoo is up to date. No new versions to add.")
        return

    print(f"[VERSION SYNC] Found {len(versions_to_add)} version(s) to add to Odoo.")

    # Calculate starting sequence based on existing count
    existing_count = odoo.execute_kw("x_payg_version", "search_count", [[]])

    for i, entry in enumerate(versions_to_add, start=1):
        version_num = str(entry.get("version", "")).strip()
        if not version_num:
            continue

        release_date = parse_date_to_odoo(entry.get("updated", ""))
        release_notes = entry.get("update_description", "")
        commit_hash = detect_git_hash(version_num)

        payload = {
            "x_name": version_num,
            "x_release_date": release_date,
            "x_release_notes": release_notes,
            "x_commit_hash": commit_hash
        }

        record_id = odoo.create("x_payg_version", payload)
        print(f"  + Added Version '{version_num}' (ID: {record_id}, Commit: {commit_hash})")

    print("[VERSION SYNC] Sync complete.")


if __name__ == "__main__":
    sync_versions_to_odoo()

