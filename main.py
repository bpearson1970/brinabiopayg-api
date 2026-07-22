# main.py version 1.04
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import os
import json
from datetime import datetime

# Load API key from environment
API_KEY = os.getenv("BRINABIOPAYG_API_KEY")

app = FastAPI()

EVENT_DIR = "/var/data/event_deposit"
os.makedirs(EVENT_DIR, exist_ok=True)

@app.get("/")
def root():
    return {"status": "ok", "message": "BrinaBio PAYG API running"}

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
