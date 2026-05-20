from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv
import datetime
import os
import itertools
import httpx

load_dotenv()  # Load environment variables from .env file

# --- FRB Configuration ---
FRB_ROUTING_NUMBER = os.environ.get("FRB_ROUTING_NUMBER", "090000515")
FRB_LEGAL_NAME = os.environ.get("FRB_LEGAL_NAME", "Federal Reserve Bank")

FEDNOW_API_BASE_URL = os.environ.get("FEDNOW_API_BASE_URL", "http://localhost:8514")

MQ_BANK_NAME = os.environ.get("MQ_BANK_NAME", "Example Bank")
MQ_BANK_RTN = os.environ.get("MQ_BANK_RTN", "000000000")
FILE_SEQUENCE = itertools.count(1)

message_queue = FastAPI(title="Message Queue API", version="1.0")

message_queue.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for subdir in ["incoming", "failed", "collected"]:
    os.makedirs(subdir, exist_ok=True)


def _save_failed_file(filename: str, contents: bytes) -> str:
    safe_name = os.path.basename(filename)
    failed_path = os.path.join("failed", safe_name)
    with open(failed_path, "wb") as handle:
        handle.write(contents)
    return failed_path


async def _send_file_to_fednow(filename: str, contents: bytes) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{FEDNOW_API_BASE_URL}/collect",
            files={"file": (filename, contents, "application/xml")},
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"FedNow returned HTTP {response.status_code}")

    try:
        payload = response.json()
    except Exception:
        payload = {}

    status = str(payload.get("status", "")).strip().lower()
    if status not in ("received", "recived"):
        raise HTTPException(status_code=502, detail=payload.get("detail") or f"FedNow rejected file with status {status or 'missing'}")

    return payload


@message_queue.get("/health", tags=["Health"])
def health_check():
    return {"status": "Message Queue API is healthy"}

@message_queue.get("/bank-info", tags=["Bank"])
def get_bank_info():
    return {
        "bank_name": MQ_BANK_NAME,
        "routing_number": MQ_BANK_RTN,
        "frb_routing_number": FRB_ROUTING_NUMBER
    }

@message_queue.post("/send", tags=["Files"])
async def send_file(
    file: UploadFile = File(...),
):
    """Send an uploaded XML file directly to FedNow."""
    try:
        contents = b""
        if not file.filename.endswith('.xml'):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")
        
        now = datetime.datetime.utcnow()
        filename = f"{MQ_BANK_RTN}_{now.strftime('%Y%m%d')}_{now.strftime('%H%M%S')}_{next(FILE_SEQUENCE):04d}.xml"
        
        contents = file.file.read()

        try:
            fednow_response = await _send_file_to_fednow(filename, contents)
        except HTTPException:
            _save_failed_file(filename, contents)
            raise
        except Exception as exc:
            _save_failed_file(filename, contents)
            raise HTTPException(status_code=502, detail=str(exc))
        
        return {
            "status": "sent",
            "filename": filename,
            "size_bytes": len(contents),
            "bank_name": MQ_BANK_NAME,
            "routing_number": MQ_BANK_RTN,
            "fednow_response": fednow_response,
        }
    except HTTPException:
        raise
    except Exception as exc:
        try:
            _save_failed_file(filename, contents)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))
    
@message_queue.post("/receive", tags=["Internal"])
def receive_file(
    file: UploadFile = File(...),
):
    """Endpoint used by FedNow to deliver files to the bank."""
    try:
        if not file.filename.lower().endswith('.xml'):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")

        contents = file.file.read()
        safe_name = os.path.basename(file.filename)
        filename = safe_name
        filepath = os.path.join("incoming", filename)

        with open(filepath, "wb") as handle:
            handle.write(contents)

        return {
            "status": "saved to incoming",
            "filename": filename,
            "size_bytes": len(contents),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@message_queue.get("/failed", tags=["Files"])
def get_failed_files():
    """List XML files in failed directory."""
    try:
        files = [f for f in os.listdir("failed") if f.endswith('.xml')]
        return {"failed_files": files}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@message_queue.get("/incoming", tags=["Files"])
def get_incoming_files():
    """List XML files in incoming directory."""
    try:
        files = [f for f in os.listdir("incoming") if f.endswith('.xml')]
        return {"incoming_files": files}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    
@message_queue.get("/failed/{filename}", tags=["Files"])
def get_failed_file(filename: str):
    """Get content of specific failed XML file."""
    try:
        if not filename.endswith('.xml'):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")
        
        filepath = os.path.join("failed", filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File not found in failed folder")

        return FileResponse(filepath, filename=filename, media_type="application/xml")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@message_queue.get("/incoming/{filename}", tags=["Files"])
def get_incoming_file(filename: str):
    """Get content of specific incoming XML file."""
    try:
        if not filename.endswith('.xml'):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")
        
        filepath = os.path.join("incoming", filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File not found in incoming folder")

        return FileResponse(filepath, filename=filename, media_type="application/xml")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@message_queue.get("/collected", tags=["Files"])
def get_collected_files():
    """List XML files in collected directory."""
    try:
        files = [f for f in os.listdir("collected") if f.endswith('.xml')]
        return {"collected_files": files}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@message_queue.get("/collected/{filename}", tags=["Files"])
def get_collected_file(filename: str):
    """Get content of specific collected XML file."""
    try:
        if not filename.endswith('.xml'):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")
        
        filepath = os.path.join("collected", filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File not found in collected folder")

        return FileResponse(filepath, filename=filename, media_type="application/xml")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@message_queue.post("/mark-failed/{filename}", tags=["Files"])
def mark_failed(filename: str):
    """Mark a file as failed."""
    try:
        if not filename.endswith('.xml'):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")

        incoming_filepath = os.path.join("incoming", filename)
        failed_filepath = os.path.join("failed", filename)

        if os.path.exists(incoming_filepath):
            os.rename(incoming_filepath, failed_filepath)
            return {"status": "marked as failed", "filename": filename}

        raise HTTPException(status_code=404, detail="File not found in incoming folder")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@message_queue.post("/mark-collected/{filename}", tags=["Files"])
def mark_collected(filename: str):
    """Mark a file as collected."""
    try:
        if not filename.endswith('.xml'):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")

        incoming_filepath = os.path.join("incoming", filename)
        failed_filepath = os.path.join("failed", filename)
        collected_filepath = os.path.join("collected", filename)

        if os.path.exists(incoming_filepath):
            os.rename(incoming_filepath, collected_filepath)
            return {"status": "marked as collected", "filename": filename}
        
        if os.path.exists(failed_filepath):
            os.rename(failed_filepath, collected_filepath)
            return {"status": "marked as collected", "filename": filename}

        if os.path.exists(collected_filepath):
            return {"status": "already marked as collected", "filename": filename}

        raise HTTPException(status_code=404, detail="File not found in any folder")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
