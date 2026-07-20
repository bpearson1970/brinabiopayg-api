from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
import json
from datetime import datetime

app = FastAPI()

EVENT_DIR = "/var/data/event_deposit"
os.makedirs(EVENT_DIR, exist_ok=True)

@app.get("/")
def root():
    return {"status": "ok", "message": "BrinaBio PAYG API running"}

@app.post("/event")
async def receive_event(request: Request):
    try:
        payload = await request.json()

        # Create filename
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        filename = f"event_{timestamp}.tmp"
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
