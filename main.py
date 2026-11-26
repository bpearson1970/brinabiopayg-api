# main.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, Response, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import json
import random
import requests
import base64
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
from contextlib import asynccontextmanager
from weasyprint import HTML

from odoo_onboard import create_onboarding_record
from services.odoo_client import odoo
from sync_versions import sync_versions_to_odoo, get_current_version

logger = logging.getLogger(__name__)

# Lifespan event handler to sync versions on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.current_version_id = False
    try:
        print("[STARTUP] Running Odoo version sync...")
        # Save the version string into FastAPI app memory (e.g. "2.06")
        app.state.current_version = sync_versions_to_odoo()
    except Exception as e:
        print(f"[STARTUP] Version sync failed: {e}")
        # Fallback: Read directly from version.json if Odoo connection fails
        app.state.current_version = get_current_version()

    # Look up the integer ID for the Many2one field
    try:
        if app.state.current_version:
            # Using your odoo client's search_read
            records = odoo.search_read(
                "x_payg_version",
                [("x_name", "=", app.state.current_version)],
                ["id"],
                limit=1
            )
            if records:
                app.state.current_version_id = records[0]["id"]
                print(f"[STARTUP] Active version ID resolved to: {app.state.current_version_id}")
            else:
                print(f"[STARTUP] Warning: No record found in x_payg_version for {app.state.current_version}")
    except Exception as e:
        print(f"[STARTUP] Could not resolve version record ID: {e}")

    yield

# Initialize FastAPI with the lifespan handler
app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory="templates")

# Read the HTML template once at startup - UNDER MAINTENANCE
with open("templates/maintenance.html", "r") as f:
    MAINTENANCE_HTML = f.read()

@app.middleware("http")
async def maintenance_middleware(request: Request, call_next):
    if os.getenv("UNDER_MAINTENANCE") == "1":
        
        # Whitelist health checks so container monitors don't panic
        if request.url.path in ["/health", "/ping"] or request.url.path.startswith("/static/"):
            return await call_next(request)

        return HTMLResponse(
            content=MAINTENANCE_HTML,
            status_code=503,
            headers={
                "Retry-After": "1800",
                "Cache-Control": "no-store"
            }
        )

    return await call_next(request)

# Ensure absolute path to version.json in project root
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE_PATH = os.path.join(BASE_DIR, "version.json")

@app.get("/version.json")
async def get_version_json():
    if os.path.exists(VERSION_FILE_PATH):
   #     return FileResponse(VERSION_FILE_PATH, media_type="application/json")
    return JSONResponse(content=[], status_code=200)

# Load API Key and Client Mapping File from environment 
API_KEY = os.getenv("BRINABIOPAYG_API_KEY")
CLIENT_MAP_FILE = os.getenv("CLIENT_MAP_FILE", "client_map.json")

# Load "static" directory
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

# Load clients for on-boarding from client_map.json
@app.get("/onboard/{client_code}")
async def onboard_form(
    request: Request,
    client_code: str
):
    with open(CLIENT_MAP_FILE) as f:
        client_map = json.load(f)

    client_info = client_map.get(client_code)

    if not client_info:
        raise HTTPException(
            status_code=404,
            detail="Unknown onboarding code"
        )

    template_name = client_info["template"]

    # --- DYNAMIC SECTION RESOLUTION START ---
    with open("section_catalog.json") as f:
        catalog = json.load(f).get("sections", {})

    client_sections = client_info.get("sections", {})
    form_sections = []

    for section_key, section_meta in catalog.items():
        version_name = client_sections.get(section_key)
        if version_name and version_name != "none":
            version_entry = section_meta.get("versions", {}).get(version_name)
            if version_entry and version_entry.get("file"):
                form_sections.append({
                    "key": section_key,
                    "title": section_meta.get("title", ""),
                    "file": f"includes/{version_entry['file']}"
                })
    # --- DYNAMIC SECTION RESOLUTION END ---

    print("Client Code:", client_code)
    print("Client ID:", client_info["client_id"])
    print("Company Name:", client_info["company_name"])
    print("Logo:", client_info["logo"])
    print("Template:", client_info["template"])
    print("Active:", client_info["active"])
    print("Form Sections:", form_sections)
    
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "client_code": client_code,
            "client_id": client_info["client_id"],
            "company_name": client_info["company_name"],
            "logo": client_info["logo"],
            "active": client_info["active"],
            "form_sections": form_sections,
            "version": request.app.state.current_version  # <--- Available in your form
        }
    )

# On-boarding Receipt
@app.get("/receipt")
async def receipt(
    request: Request,
    submission_reference: str = "",
    company_name: str = "",
    submitted_by: str = "",
    version: str = "",
    submitted_timestamp: str = "",
    active: str = ""
):
    with open("./static/images/BrinaBioPAYG.png", "rb") as f:
        bbpayg_logo = base64.b64encode(f.read()).decode("utf-8")

    with open("./static/images/BrinaMedical.png", "rb") as f:
        brina_logo = base64.b64encode(f.read()).decode("utf-8")
        
    ip_address = request.client.host
    user_agent_raw = request.headers.get("user-agent", "")
    user_agent = parse_user_agent(user_agent_raw)
    
    return templates.TemplateResponse(
        request=request,
        name="brinapayg_onboard_receipt.html",
        context={
            "submission_reference": submission_reference,
            "company_name": company_name,
            "submitted_by": submitted_by,
            "version": version,
            "submitted_timestamp": submitted_timestamp,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "active": active,
            "header_logo": bbpayg_logo,
            "footer_logo": brina_logo
        }
    )

# Create receipt PDF
@app.post("/generate-receipt-pdf")
async def receipt_pdf(request: Request):
    data = await request.json()
    ip_address = request.client.host
    user_agent_raw = request.headers.get("user-agent", "")
    user_agent = parse_user_agent(user_agent_raw)

    with open("./static/images/BrinaBioPAYG.png", "rb") as f:
        bbpayg_logo = base64.b64encode(f.read()).decode("utf-8")

    with open("./static/images/BrinaMedical.png", "rb") as f:
        brina_logo = base64.b64encode(f.read()).decode("utf-8")
    
    html_content = templates.get_template(
        "brinapayg_onboard_receipt.html"
    ).render(
        submission_reference=data["submission_reference"],
        company_name=data["company_name"],
        submitted_by=data["submitted_by"],
        version=data["version"],
        submitted_timestamp=data["submitted_timestamp"],
        active=data["active_value"],
        ip_address=ip_address,
        user_agent=user_agent,
        header_logo=bbpayg_logo,
        footer_logo=brina_logo
    )

    pdf = HTML(string=html_content).write_pdf(zoom=0.8)
    print("Receipt HTML rendered successfully")

    pdf_base64 = base64.b64encode(pdf).decode("utf-8")
    
    filename = (
        f"PAYG_Submission_Receipt_"
        f"{data['submission_reference']}.pdf"
    )
    
    return {
        "success": True,
        "submission_reference": data["submission_reference"],
        "filename": filename,
        "pdf_base64": pdf_base64
    }

def parse_user_agent(user_agent: str) -> str:
    browser = "Unknown Browser"
    operating_system = "Unknown OS"

    if "Edg/" in user_agent:
        browser = "Microsoft Edge"
    elif "Chrome/" in user_agent:
        browser = "Google Chrome"
    elif "Firefox/" in user_agent:
        browser = "Mozilla Firefox"
    elif "Safari/" in user_agent and "Chrome/" not in user_agent:
        browser = "Safari"

    if "Windows NT 10.0" in user_agent:
        operating_system = "Windows 10/11"
    elif "Android" in user_agent:
        operating_system = "Android"
    elif "iPhone" in user_agent:
        operating_system = "iPhone"
    elif "iPad" in user_agent:
        operating_system = "iPad"
    elif "Mac OS X" in user_agent:
        operating_system = "macOS"

    return f"{browser} on {operating_system}"

# Define deposit and onboarding directories
EVENT_DIR = "/var/data/event_deposit"
os.makedirs(EVENT_DIR, exist_ok=True)

LOG_DIR = "/var/data/log_deposit"
os.makedirs(LOG_DIR, exist_ok=True)

ONBOARD_DIR = "/var/data/onboard"
os.makedirs(ONBOARD_DIR, exist_ok=True)

ONBOARDSub_DIR = "/var/data/onboard/submissions"
os.makedirs(ONBOARDSub_DIR, exist_ok=True)

ODOOReceipt_DIR = "/var/data/onboard/odoo_receipts"
os.makedirs(ODOOReceipt_DIR, exist_ok=True)

# Testing endpoints
@app.get("/")
def root():
    return {"status": "ok", "message": "BrinaBio PAYG API running"}

@app.get("/onboard")
async def onboard_status():
    return {
        "status": "ok",
        "message": "Onboarding endpoint ready"
    }

# App definitions
@app.post("/onboard")
async def onboard_submit(request: Request):
    payload = await request.json()

    payload["x_ip_address"] = request.client.host
    payload["x_user_agent"] = parse_user_agent(
        request.headers.get("user-agent", "")
    )

    submission_reference = payload.get("x_submit_reference")

    if not submission_reference:
        return {
            "success": False,
            "message": "Submission reference missing."
        }

    file_name = os.path.join(ONBOARDSub_DIR, f"{submission_reference}.json")
    print(f"Writing file: {file_name}")
    
    with open(file_name, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4)
        
    odoo_record_id = create_onboarding_record(payload)

    print(f"Odoo Record Created: {odoo_record_id}")
    
    return {
        "success": True,
        "submission_reference": payload["x_submit_reference"],
        "odoo_record_id": odoo_record_id
    }

@app.post("/event")
async def receive_event(request: Request):
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        payload = await request.json()

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        rand = random.randint(10000, 99999)
        filename = f"event_{timestamp}_{rand}.tmp"
        filepath = os.path.join(EVENT_DIR, filename)

        with open(filepath, "w") as f:
            json.dump(payload, f)

        return {"status": "success", "file": filename}

    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )

@app.post("/log")
async def receive_log(request: Request):
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        payload = await request.json()

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        rand = random.randint(10000, 99999)
        filename = f"logdump_{timestamp}_{rand}.tmp"
        filepath = os.path.join(LOG_DIR, filename)

        with open(filepath, "w") as f:
            json.dump(payload, f)

        return {"status": "success", "file": filename}

    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )
