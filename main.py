# main.py version 1.06

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import os
import json
import random
import xml.etree.ElementTree as ET
from datetime import datetime

# Load API key from environment
API_KEY = os.getenv("BRINABIOPAYG_API_KEY")

app = FastAPI()

# Define the Endpoints
EVENT_DIR = "/var/data/event_deposit"
os.makedirs(EVENT_DIR, exist_ok=True)

LOG_DIR = "/var/data/log_deposit"
os.makedirs(LOG_DIR, exist_ok=True)

ONBOARD_DIR = "/var/data/onboard"
os.makedirs(ONBOARD_DIR, exist_ok=True)

#Testing directories are there

@app.get("/")
def root():
    return {"status": "ok", "message": "BrinaBio PAYG API running"}

@app.get("/onboard")
async def onboard_test():
    return {
        "status": "ok",
        "message": "Onboarding endpoint ready"
    }

#App definitions

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

@app.post("/onboard")
async def onboard_application(request: Request):
    try:
        raw = await request.body()
        print("CONTENT TYPE:", request.headers.get("content-type"))
        print(raw.decode("utf-8"))

        xml = raw.decode("utf-8")

        root = ET.fromstring(xml)

        fields = {}

        for field in root.findall(".//{http://ns.adobe.com/xfdf/}field"):
            name = field.attrib.get("name")

            value = field.find(
                "{http://ns.adobe.com/xfdf/}value"
            )

            fields[name] = (
                value.text if value is not None else None
            )

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        rand = random.randint(10000, 99999)

        filename = f"onboard_{timestamp}_{rand}.json"
        filepath = os.path.join(ONBOARD_DIR, filename)

        with open(filepath, "w") as f:
            json.dump(fields, f, indent=2)

        print("Received onboarding fields:", fields)

        return PlainTextResponse("Form successfully submitted")
        
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": str(e)
            }
        )
