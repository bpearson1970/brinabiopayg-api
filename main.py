# main.py version 1.07

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import os
import json
import random
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

# Load API key from environment
API_KEY = os.getenv("BRINABIOPAYG_API_KEY")

app = FastAPI()

# Load "static" directory
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

# Create ODOO connectivity test
@app.get("/test-odoo")
async def test_odoo():

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

    return response.json()

# Load clients for on-boarding from client_map.json
@app.get("/onboard/{client_code}")
async def onboard_form(
    request: Request,
    client_code: str
):
    with open("client_map.json") as f:
        client_map = json.load(f)

    client_info = client_map.get(client_code)

    if not client_info:
        raise HTTPException(
            status_code=404,
            detail="Unknown onboarding code"
        )

    template_name = client_info["template"]

    print("Client Code:", client_code)
    print("Client ID:", client_info["client_id"])
    print("Company Name:", client_info["company_name"])
    print("Logo:", client_info["logo"])
    print("Template:", client_info["template"])
    print("Active:", client_info["active"])
    
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "client_code": client_code,
            "client_id": client_info["client_id"],
            "company_name": client_info["company_name"],
            "logo": client_info["logo"],
            "active": client_info["active"]
        }
    )
    print(type(request))    

#On-boarding Receipt
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
    
    ip_address = request.client.host

    user_agent_raw = request.headers.get(
        "user-agent", ""
    )

    user_agent = parse_user_agent( user_agent_raw )
    
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
            "active": active
        }
    )

def parse_user_agent(user_agent: str) -> str:

    browser = "Unknown Browser"
    operating_system = "Unknown OS"

    # Browser

    if "Edg/" in user_agent:
        browser = "Microsoft Edge"
    elif "Chrome/" in user_agent:
        browser = "Google Chrome"
    elif "Firefox/" in user_agent:
        browser = "Mozilla Firefox"
    elif "Safari/" in user_agent and "Chrome/" not in user_agent:
        browser = "Safari"

    # Operating System

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


# Define the Endpoints
EVENT_DIR = "/var/data/event_deposit"
os.makedirs(EVENT_DIR, exist_ok=True)

LOG_DIR = "/var/data/log_deposit"
os.makedirs(LOG_DIR, exist_ok=True)

ONBOARD_DIR = "/var/data/onboard"
os.makedirs(ONBOARD_DIR, exist_ok=True)

ONBOARDSub_DIR = "/var/data/onboard/submissions"
os.makedirs(ONBOARDSub_DIR, exist_ok=True)

# Testing directories exist

@app.get("/")
def root():
    return {"status": "ok", "message": "BrinaBio PAYG API running"}

@app.get("/onboard")
async def onboard_submit():
    return {
        "status": "ok",
        "message": "Onboarding endpoint ready"
    }

#App definitions

@app.post("/onboard")
async def onboard_submit(
    request: Request
):
    payload = await request.json()

    payload["x_ip_address"] = request.client.host
    payload["x_user_agent"] = parse_user_agent(
        request.headers.get(
            "user-agent",
            ""
        )
    )

    submission_reference = payload.get(
        "x_submit_reference"
    )

    if not submission_reference:
        return {
            "success": False,
            "message":
                "Submission reference missing."
        }

    file_name = os.path.join( ONBOARDSub_DIR , f"{submission_reference}.json"
    )

    print(f"Writing file: {file_name}")
    
    with open(
        file_name,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            payload,
            file,
            indent=4
        )
          
    return {
        "success": True
    }

@app.post("/event")
async def receive_event(request: Request):
    # Authorization check
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        payload = await request.json()

        # Create filename
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        rand = random.randint(10000, 99999)
        filename = f"event_{timestamp}_{rand}.tmp"
        filepath = os.path.join(EVENT_DIR, filename)

        # Write JSON payload to file
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
    # Authorization check
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        payload = await request.json()

        # Create filename
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        rand = random.randint(10000, 99999)
        filename = f"logdump_{timestamp}_{rand}.tmp"
        filepath = os.path.join(LOG_DIR, filename)

        # Write JSON payload to file
        with open(filepath, "w") as f:
            json.dump(payload, f)

        return {"status": "success", "file": filename}

    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )

