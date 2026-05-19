from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
from urllib import error, request
import json
import uuid
import os

os.makedirs("collected", exist_ok=True)

load_dotenv()  # Load environment variables from .env file

# --- FRB Configuration ---
FRB_ROUTING_NUMBER = os.environ.get("FRB_ROUTING_NUMBER", "090000515")
FRB_LEGAL_NAME = os.environ.get("FRB_LEGAL_NAME", "Federal Reserve Bank")

MQ_BANK0_RTN = os.environ.get("MQ_BANK0_RTN", "111111111")
MQ_BANK1_RTN = os.environ.get("MQ_BANK1_RTN", "222222222")
MQ_BANK2_RTN = os.environ.get("MQ_BANK2_RTN", "333333333")
MQ_BANK3_RTN = os.environ.get("MQ_BANK3_RTN", "444444444")

MQ_BANK0_URL = os.environ.get("MQ_BANK0_URL", "message-queue-bank0-client:8000")
MQ_BANK1_URL = os.environ.get("MQ_BANK1_URL", "message-queue-bank1-client:8000")
MQ_BANK2_URL = os.environ.get("MQ_BANK2_URL", "message-queue-bank2-client:8000")
MQ_BANK3_URL = os.environ.get("MQ_BANK3_URL", "message-queue-bank3-client:8000")

SCRIPT_DIR = Path(__file__).resolve().parent
RANDOM_SAMPLE_XML_PATH = SCRIPT_DIR / "random_sample.xml"

fednow = FastAPI(title="FedNow API", version="1.0")

fednow.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@fednow.get("/health", tags=["Health"])
def health_check():
    return {"status": "FedNow API is healthy"}

@fednow.get("/frb-info", tags=["FRB"])
def get_frb_info():
    return {
        "routing_number": FRB_ROUTING_NUMBER,
        "legal_name": FRB_LEGAL_NAME
    }

@fednow.post("/collect", tags=["Messages"])
def collect_message(file: UploadFile = File(...)):
    """Save an uploaded XML file into the collected directory for now."""
    try:
        if not file.filename.lower().endswith(".xml"):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")

        contents = file.file.read()
        filepath = os.path.join("collected", file.filename)

        with open(filepath, "wb") as handle:
            handle.write(contents)

        return {
            "status": "received",
            "filename": file.filename,
            "size_bytes": len(contents),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    
def _build_multipart_file_body(field_name: str, filename: str, contents: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            f"Content-Type: application/xml\r\n\r\n"
        ).encode("utf-8"),
        contents,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts), boundary


@fednow.post("/send-message", tags=["Messages"])
def send_message():
    """Send the local random_sample.xml file to the first bank endpoint."""
    if not RANDOM_SAMPLE_XML_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Missing sample file: {RANDOM_SAMPLE_XML_PATH.name}")

    source_filename = RANDOM_SAMPLE_XML_PATH.name
    contents = RANDOM_SAMPLE_XML_PATH.read_bytes()
    body, boundary = _build_multipart_file_body("file", source_filename, contents)
    target_url = MQ_BANK0_URL + "/receive"

    http_request = request.Request(target_url, data=body, method="POST")
    http_request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    http_request.add_header("Content-Length", str(len(body)))

    try:
        with request.urlopen(http_request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            try:
                parsed_body = json.loads(response_body)
            except json.JSONDecodeError:
                parsed_body = {"raw_response": response_body}

            return {
                "status": "sent",
                "source_file": source_filename,
                "target_url": target_url,
                "downstream_status": response.status,
                "downstream_response": parsed_body,
            }
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=exc.code, detail=detail)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    