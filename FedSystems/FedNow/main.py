import datetime
from logging import DEBUG
from typing import List, Optional, Union
from venv import logger
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path
from urllib import error, request
import json
import uuid
import os
from lxml import etree
from io import BytesIO
import psycopg2
import psycopg2.extras

os.makedirs("collected", exist_ok=True)

load_dotenv()  # Load environment variables from .env file

DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1", "t")
XSD_VALIDATION = os.environ.get("XSD_VALIDATION", "True").lower() in ("true", "1", "t")

# Schemas
pacs008_xsd_path = Path(__file__).parent / "schemas/pacs.008.xsd"
pacs002_xsd_path = Path(__file__).parent / "schemas/pacs.002.xsd"
pain013_xsd_path = Path(__file__).parent / "schemas/pain.013.xsd"
pain014_xsd_path = Path(__file__).parent / "schemas/pain.014.xsd"

with open(pacs008_xsd_path, "rb") as f:
    pacs008_schema_doc = etree.parse(f)
    pacs008_schema = etree.XMLSchema(pacs008_schema_doc)

with open(pacs002_xsd_path, "rb") as f:
    pacs002_schema_doc = etree.parse(f)
    pacs002_schema = etree.XMLSchema(pacs002_schema_doc)

with open(pain013_xsd_path, "rb") as f:
    pain013_schema_doc = etree.parse(f)
    pain013_schema = etree.XMLSchema(pain013_schema_doc)

with open(pain014_xsd_path, "rb") as f:
    pain014_schema_doc = etree.parse(f)
    pain014_schema = etree.XMLSchema(pain014_schema_doc)

if DEBUG:
    if XSD_VALIDATION:
        print("XSD validation is enabled. XML files will be validated against the schemas.")
        # Print schema:
        with open(pacs008_xsd_path, "r") as f:
            print("PACS 008 XSD Schema:")
            print(f.read())
        
        with open(pacs002_xsd_path, "r") as f:
            print("PACS 002 XSD Schema:")
            print(f.read())

        with open(pain013_xsd_path, "r") as f:
            print("PAIN 013 XSD Schema:")
            print(f.read())

        with open(pain014_xsd_path, "r") as f:
            print("PAIN 014 XSD Schema:")
            print(f.read())
    else:
        print("XSD validation is disabled. XML files will not be validated against the schemas.")

# --- FRB Configuration ---
FRB_ROUTING_NUMBER = os.environ.get("FRB_ROUTING_NUMBER", "090000515")
FRB_LEGAL_NAME = os.environ.get("FRB_LEGAL_NAME", "Federal Reserve Bank")

MQ_BANK0_RTN = os.environ.get("MQ_BANK0_RTN", "111111111")
MQ_BANK1_RTN = os.environ.get("MQ_BANK1_RTN", "222222222")
MQ_BANK2_RTN = os.environ.get("MQ_BANK2_RTN", "333333333")
MQ_BANK3_RTN = os.environ.get("MQ_BANK3_RTN", "444444444")
MQ_BANK4_RTN = os.environ.get("MQ_BANK4_RTN", "555555555")
MQ_BANK5_RTN = os.environ.get("MQ_BANK5_RTN", "666666666")

MQ_BANK0_URL = os.environ.get("MQ_BANK0_URL", "message-queue-bank0-client:8000")
MQ_BANK1_URL = os.environ.get("MQ_BANK1_URL", "message-queue-bank1-client:8000")
MQ_BANK2_URL = os.environ.get("MQ_BANK2_URL", "message-queue-bank2-client:8000")
MQ_BANK3_URL = os.environ.get("MQ_BANK3_URL", "message-queue-bank3-client:8000")
MQ_BANK4_URL = os.environ.get("MQ_BANK4_URL", "message-queue-bank4-client:8000")
MQ_BANK5_URL = os.environ.get("MQ_BANK5_URL", "message-queue-bank5-client:8000")

MQ_BANK0_LEGAL_NAME = os.environ.get("MQ_BANK0_LEGAL_NAME", "Bank 0")
MQ_BANK1_LEGAL_NAME = os.environ.get("MQ_BANK1_LEGAL_NAME", "Bank 1")
MQ_BANK2_LEGAL_NAME = os.environ.get("MQ_BANK2_LEGAL_NAME", "Bank 2")
MQ_BANK3_LEGAL_NAME = os.environ.get("MQ_BANK3_LEGAL_NAME", "Bank 3")
MQ_BANK4_LEGAL_NAME = os.environ.get("MQ_BANK4_LEGAL_NAME", "Bank 4")
MQ_BANK5_LEGAL_NAME = os.environ.get("MQ_BANK5_LEGAL_NAME", "Bank 5")

MQ_BANK0_PORT = os.environ.get("MQ_BANK0_PORT", "8000")
MQ_BANK1_PORT = os.environ.get("MQ_BANK1_PORT", "8000")
MQ_BANK2_PORT = os.environ.get("MQ_BANK2_PORT", "8000")
MQ_BANK3_PORT = os.environ.get("MQ_BANK3_PORT", "8000")
MQ_BANK4_PORT = os.environ.get("MQ_BANK4_PORT", "8000")
MQ_BANK5_PORT = os.environ.get("MQ_BANK5_PORT", "8000")

MERCHANT0_NAME = os.environ.get("MERCHANT0_NAME", "Selle")
MQ_MERCHANT0_PORT = os.environ.get("MQ_MERCHANT0_PORT", "8713")
MQ_MERCHANT0_URL = os.environ.get("MQ_MERCHANT0_URL", "message-queue-merchant0-client:8000")

banks_ports_map = {
    MQ_BANK0_RTN: MQ_BANK0_URL,
    MQ_BANK1_RTN: MQ_BANK1_URL,
    MQ_BANK2_RTN: MQ_BANK2_URL,
    MQ_BANK3_RTN: MQ_BANK3_URL,
    MQ_BANK4_RTN: MQ_BANK4_URL,
    MQ_BANK5_RTN: MQ_BANK5_URL,
    MERCHANT0_NAME: MQ_MERCHANT0_URL,
}

port_maps = {
    MQ_BANK0_RTN: MQ_BANK0_PORT,
    MQ_BANK1_RTN: MQ_BANK1_PORT,
    MQ_BANK2_RTN: MQ_BANK2_PORT,
    MQ_BANK3_RTN: MQ_BANK3_PORT,
    MQ_BANK4_RTN: MQ_BANK4_PORT,
    MQ_BANK5_RTN: MQ_BANK5_PORT,
    MERCHANT0_NAME: MQ_MERCHANT0_PORT,
}

port_to_name_map = {
    MQ_BANK0_PORT: MQ_BANK0_LEGAL_NAME,
    MQ_BANK1_PORT: MQ_BANK1_LEGAL_NAME,
    MQ_BANK2_PORT: MQ_BANK2_LEGAL_NAME,
    MQ_BANK3_PORT: MQ_BANK3_LEGAL_NAME,
    MQ_BANK4_PORT: MQ_BANK4_LEGAL_NAME,
    MQ_BANK5_PORT: MQ_BANK5_LEGAL_NAME,
    MQ_MERCHANT0_PORT: MERCHANT0_NAME,
}

merchants_ports_map = {
    MERCHANT0_NAME: MQ_MERCHANT0_URL,
}

SCRIPT_DIR = Path(__file__).resolve().parent
RANDOM_SAMPLE_XML_PATH = SCRIPT_DIR / "random_sample.xml"
SCHEMAS_DIR = SCRIPT_DIR / "schemas"

fednow = FastAPI(title="FedNow API", version="1.0")

fednow.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class pacs008Message(BaseModel):
    msg_id: str
    dbtr_rtn: str
    cdtr_rtn: str
    amount: float
    end_to_end_id: str
    file_content: bytes

class pacs002Message(BaseModel):
    msg_id: str
    dbtr_rtn: str
    cdtr_rtn: str
    amount: float
    status: str
    end_to_end_id: str
    file_content: bytes

class pain013Message(BaseModel):
    msg_id: str
    dbtr_rtn: str
    cdtr_rtn: str
    amount: float
    end_to_end_id: str
    file_content: bytes

class pain014Message(BaseModel):
    msg_id: str
    status: str
    end_to_end_id: str
    file_content: bytes

class messageQueueObj(BaseModel):
    timestamp: datetime.datetime = Field(..., description="Timestamp of the transaction in ISO 8601 format")
    status: str = Field(..., description="Current status of the transaction, e.g., 'ACCP' for accepted, 'RJCT' for rejected")
    endToEndId: str = Field(..., description="Unique identifier for the transaction, used for tracking and reconciliation")
    dbtr_rtn: str = Field(..., description="Routing number of the debtor/sender bank")
    cdtr_rtn: str = Field(..., description="Routing number of the creditor/receiving bank")
    amount: float = Field(..., description="Amount of the transaction in USD")
    interested_parties: Optional[list[str]] = Field(None, description="List of additional interested parties for notifications, e.g., merchants or regulators.")
    pacs008_file: Optional[pacs008Message] = Field(None, description="The original pacs.008 file content, required for credit transfer messages")
    pacs002_file: Optional[pacs002Message] = Field(None, description="The original pacs.002 file content, required for payment status reports")
    pain013_file: Optional[pain013Message] = Field(None, description="The original pain.013 file content, optional for additional processing")
    pain014_file: Optional[pain014Message] = Field(None, description="The original pain.014 file content, optional for additional processing")

pending_messages = []
completed_messages = []

@fednow.get("/messages/pending", tags=["DEBUG"])
def get_pending_messages():
    return pending_messages

@fednow.get("/messages/completed", tags=["DEBUG"])
def get_completed_messages():
    return completed_messages

@fednow.get("/")
def root():
    return {"message": "Welcome to the FedNow API - use /docs for API documentation"}

@fednow.get("/health", tags=["Health"])
def health_check():
    return {"status": "FedNow API is healthy"}

@fednow.get("/frb-info", tags=["FRB"])
def get_frb_info():
    return {
        "routing_number": FRB_ROUTING_NUMBER,
        "legal_name": FRB_LEGAL_NAME
    }

@fednow.get("/banks", tags=["Banks"])
def list_banks():
    return [
        {"routing_number": MQ_BANK0_RTN, "legal_name": MQ_BANK0_LEGAL_NAME, "port": MQ_BANK0_PORT},
        {"routing_number": MQ_BANK1_RTN, "legal_name": MQ_BANK1_LEGAL_NAME, "port": MQ_BANK1_PORT},
        {"routing_number": MQ_BANK2_RTN, "legal_name": MQ_BANK2_LEGAL_NAME, "port": MQ_BANK2_PORT},
        {"routing_number": MQ_BANK3_RTN, "legal_name": MQ_BANK3_LEGAL_NAME, "port": MQ_BANK3_PORT},
        {"routing_number": MQ_BANK4_RTN, "legal_name": MQ_BANK4_LEGAL_NAME, "port": MQ_BANK4_PORT},
        {"routing_number": MQ_BANK5_RTN, "legal_name": MQ_BANK5_LEGAL_NAME, "port": MQ_BANK5_PORT},
        {"routing_number": "No RTN", "legal_name": os.environ.get("MERCHANT0_NAME", "Selle"), "port": os.environ.get("MQ_MERCHANT0_PORT", "8713")}
    ]

@fednow.post("/collect", tags=["Messages"])
def collect_message(file: UploadFile = File(...), sender_port: str = Form(..., description="Port number of the sender, used for authorization and logging")):
    """Save an uploaded XML file into the collected directory after formal validation."""
    try:
        if not file.filename.lower().endswith(".xml"):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")

        contents = file.file.read()

        if DEBUG:
            print(f"Received file: {file.filename}, size: {len(contents)} bytes, sender_port: {sender_port}")

        validation_status = validate_xml(contents, file.filename, sender_port = sender_port)

        filepath = os.path.join("collected", file.filename)
        with open(filepath, "wb") as handle:
            handle.write(contents)

        return_response = process_file(contents, file.filename, sender_port = sender_port)

        if DEBUG:
            print(f"File {file.filename} processed successfully. Validation status: {validation_status}")
        
        if return_response is None:
            return {
                "status": "received and sent",
                "filename": file.filename,
                "size_bytes": len(contents),
                "validation": validation_status,
            }

        return return_response
        
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"An error occurred while processing the file: {str(exc)}")

def are_banks_registered(bank_rtns: list[str]) -> bool:
    """Check if all bank RTNs in the list are registered in our system."""
    for rtn in bank_rtns:
        if rtn not in banks_ports_map:
            return False
    return True

def validate_pacs008_xml(tree, root, sender_port=None) -> bool:
    # Validate pacs.008 structure
    # Validate using XSD schema pacs008_schema
    if not pacs008_schema.validate(tree) and XSD_VALIDATION:
        errors = [str(error) for error in pacs008_schema.error_log]
        raise HTTPException(status_code=400, detail=f"pacs.008 XML does not conform to schema: {errors}")

    cdtr_rtn = root.find(".//{*}CdtTrfTxInf/{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
    dbtr_rtn = root.find(".//{*}CdtTrfTxInf/{*}DbtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
    amount = root.find(".//{*}CdtTrfTxInf/{*}IntrBkSttlmAmt")
    end_to_end_id = root.find(".//{*}CdtTrfTxInf/{*}PmtId/{*}EndToEndId")

    # Make sure sender_port matches the dbtr_rtn if sender_port is provided (for better logging and debugging)
    if sender_port is not None and dbtr_rtn is not None:
        expected_sender_port = port_maps.get(dbtr_rtn.text)
        if expected_sender_port is not None and sender_port != expected_sender_port:
            raise HTTPException(status_code=400, detail=f"You are not authorized to send pacs.008 message with this dbtr rtn. Sender port {sender_port} does not match expected port {expected_sender_port} for debtor RTN {dbtr_rtn.text}. Check /bank-info and make sure you're using the correct MQ for your bank.")

    # check if both rtns are registered banks
    if not are_banks_registered([cdtr_rtn.text if cdtr_rtn is not None else None, dbtr_rtn.text if dbtr_rtn is not None else None]):
        raise HTTPException(status_code=400, detail=f"Unknown bank RTN(s): {', '.join([rtn.text for rtn in [cdtr_rtn, dbtr_rtn] if rtn is not None and rtn.text not in banks_ports_map])}")
    
    if DEBUG:
        print("PACS 008 Validation Passed:")
        print(f"Creditor RTN: {cdtr_rtn.text if cdtr_rtn is not None else 'Not found'}")
        print(f"Debtor RTN: {dbtr_rtn.text if dbtr_rtn is not None else 'Not found'}")
        print(f"Amount: {amount.text if amount is not None else 'Not found'}")
        print(f"End-to-End ID: {end_to_end_id.text if end_to_end_id is not None else 'Not found'}")

    if cdtr_rtn is None or dbtr_rtn is None or amount is None or end_to_end_id is None:
        raise HTTPException(status_code=400, detail="Invalid pacs.008 structure")
    return "Valid pacs.008"

def validate_pacs002_xml(tree, root, sender_port=None) -> bool:
    # Validate pacs.002 structure
    if not pacs002_schema.validate(tree) and XSD_VALIDATION:
        errors = [str(error) for error in pacs002_schema.error_log]
        raise HTTPException(status_code=400, detail=f"pacs.002 XML does not conform to schema: {errors}")

    msg_id = root.find(".//{*}GrpHdr/{*}MsgId")
    dbtr_rtn = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}DbtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
    cdtr_rtn = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
    amount = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}IntrBkSttlmAmt")
    status = root.find(".//{*}TxInfAndSts/{*}TxSts")
    end_to_end_id = root.find(".//{*}TxInfAndSts/{*}OrgnlEndToEndId")

    # Make sure sender_port matches the cdtr_rtn if sender_port is provided (for better logging and debugging)
    if DEBUG:
        print (f"Validating pacs.002 with sender_port: {sender_port}, cdtr_rtn: {cdtr_rtn.text if cdtr_rtn is not None else 'Not found'}")
    if sender_port is not None and cdtr_rtn is not None:
        expected_sender_port = port_maps.get(cdtr_rtn.text)
        if expected_sender_port is not None and sender_port != expected_sender_port:
            raise HTTPException(status_code=400, detail=f"You are not authorized to send pacs.002 message with this cdtr rtn. Sender port {sender_port} does not match expected port {expected_sender_port} for creditor RTN {cdtr_rtn.text}. Check /bank-info and make sure you're using the correct MQ for your bank")

    # check if both rtns are registered banks
    if not are_banks_registered([cdtr_rtn.text if cdtr_rtn is not None else None, dbtr_rtn.text if dbtr_rtn is not None else None]):
        raise HTTPException(status_code=400, detail=f"Unknown bank RTN(s): {', '.join([rtn.text for rtn in [cdtr_rtn, dbtr_rtn] if rtn is not None and rtn.text not in banks_ports_map])}")
    
    if DEBUG:
        print("PACS 002 Validation Passed:")
        print(f"Message ID: {msg_id.text if msg_id is not None else 'Not found'}")
        print(f"Debtor RTN: {dbtr_rtn.text if dbtr_rtn is not None else 'Not found'}")
        print(f"Creditor RTN: {cdtr_rtn.text if cdtr_rtn is not None else 'Not found'}")
        print(f"Amount: {amount.text if amount is not None else 'Not found'}")
        print(f"Status: {status.text if status is not None else 'Not found'}")
        print(f"End-to-End ID: {end_to_end_id.text if end_to_end_id is not None else 'Not found'}")

    if msg_id is None or dbtr_rtn is None or amount is None or status is None or end_to_end_id is None:
        raise HTTPException(status_code=400, detail="Invalid pacs.002 structure")
    return "Valid pacs.002"

def validate_pain013_xml(tree, root) -> bool:
    # Validate pain.013 structure
    if not pain013_schema.validate(tree) and XSD_VALIDATION:
        errors = [str(error) for error in pain013_schema.error_log]
        raise HTTPException(status_code=400, detail=f"pain.013 XML does not conform to schema: {errors}")

    msg_id = root.find(".//{*}GrpHdr/{*}MsgId")
    dbtr_rtn = root.find(".//{*}DbtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
    cdtr_rtn = root.find(".//{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
    amount = root.find(".//{*}InstdAmt")
    end_to_end_id = root.find(".//{*}PmtId/{*}EndToEndId")
    
    # check if both rtns are registered banks
    if not are_banks_registered([cdtr_rtn.text if cdtr_rtn is not None else None, dbtr_rtn.text if dbtr_rtn is not None else None]):
        raise HTTPException(status_code=400, detail=f"Unknown bank RTN(s): {', '.join([rtn.text for rtn in [cdtr_rtn, dbtr_rtn] if rtn is not None and rtn.text not in banks_ports_map])}")
    
    if DEBUG:
        print("PAIN 013 Validation Passed:")
        print(f"Message ID: {msg_id.text if msg_id is not None else 'Not found'}")
        print(f"Debtor RTN: {dbtr_rtn.text if dbtr_rtn is not None else 'Not found'}")
        print(f"Creditor RTN: {cdtr_rtn.text if cdtr_rtn is not None else 'Not found'}")
        print(f"Amount: {amount.text if amount is not None else 'Not found'}")
        print(f"End-to-End ID: {end_to_end_id.text if end_to_end_id is not None else 'Not found'}")

    if msg_id is None or dbtr_rtn is None or amount is None or end_to_end_id is None:
        raise HTTPException(status_code=400, detail="Invalid pain.013 structure")
    return "Valid pain.013"

def validate_pain014_xml(tree, root) -> bool:
    # Validate pain.014 structure
    if not pain014_schema.validate(tree) and XSD_VALIDATION:
        errors = [str(error) for error in pain014_schema.error_log]
        raise HTTPException(status_code=400, detail=f"pain.014 XML does not conform to schema: {errors}")
    
    msg_id = root.find(".//{*}GrpHdr/{*}MsgId")
    end_to_end_id = root.find(".//{*}TxInfAndSts/{*}OrgnlEndToEndId")
    status = root.find(".//{*}TxInfAndSts/{*}TxSts")

    if DEBUG:
        print("PAIN 014 Validation Passed:")
        print(f"Message ID: {msg_id.text if msg_id is not None else 'Not found'}")
        print(f"End-to-End ID: {end_to_end_id.text if end_to_end_id is not None else 'Not found'}")
        print(f"Status: {status.text if status is not None else 'Not found'}")

    if msg_id is None or end_to_end_id is None or status is None:
        raise HTTPException(status_code=400, detail="Invalid pain.014 structure")
    return "Valid pain.014"

def validate_xml(contents: bytes, filename: str, sender_port: Optional[str] = None) -> str:
    try:
        if not filename.endswith(".xml"):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")

        tree = etree.parse(BytesIO(contents))
        root = tree.getroot()
        if root.tag.endswith("Document"):
            ns = root.nsmap.get(None)  # Get default namespace
            if ns == "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08":
                return validate_pacs008_xml(tree, root, sender_port = sender_port)
            elif ns == "urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10":
                return validate_pacs002_xml(tree, root, sender_port = sender_port)
            elif ns == "urn:iso:std:iso:20022:tech:xsd:pain.013.001.07":
                return validate_pain013_xml(tree, root)
            elif ns == "urn:iso:std:iso:20022:tech:xsd:pain.014.001.07":
                return validate_pain014_xml(tree, root)
            else:
                raise HTTPException(status_code=400, detail="Unknown XML namespace")
        else:
            raise HTTPException(status_code=400, detail="Root element must be Document")
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"XML syntax error: {str(exc)}")

class FundsTransferRequest(BaseModel):
    sender_master_account_rtn: str
    receiver_master_account_rtn: str
    amount_cents: float
    rail_type: str
    external_ref_id: Optional[str] = None
    effective_date: Optional[str] = None
 
def transfer_funds(sending_bank_rtn: str, receiving_bank_rtn: str, amount_cents: float, rail_type: str = "FedNow", external_ref_id: Optional[str] = None, effective_date: Optional[str] = None):
    """Transfers funds between two accounts when a message is accepted."""
    if effective_date is None:
        effective_date = datetime.datetime.utcnow().date().isoformat()
    
    data = FundsTransferRequest(
        sender_master_account_rtn=sending_bank_rtn,
        receiver_master_account_rtn=receiving_bank_rtn,
        amount_cents=amount_cents,
        rail_type=rail_type,
        external_ref_id=external_ref_id,
        effective_date=effective_date
    )
    return funds_transfer(data)

def funds_transfer(transfer_data: FundsTransferRequest):
    """Create transfer ledger entries and update running balances.

    Required JSON keys:
      - sender_master_account_rtn
      - receiver_master_account_rtn
            - amount_cents
      - rail_type

    Optional:
      - external_ref_id
      - effective_date

        For ACH/FedNow rails, this writes two ledger rows:
            1) credit leg: receiver as `master_account_rtn`, sender as `activity_source_rtn`
            2) debit leg: sender as `master_account_rtn`, receiver as `activity_source_rtn`
        and applies both running balance updates.

        For other rails, this writes one ledger row where `master_account_rtn`
        is the registered bank and `activity_source_rtn` is the outside bank,
        then updates running balance only for the registered bank.
    """
    required = [
        "sender_master_account_rtn",
        "receiver_master_account_rtn",
        "amount_cents",
        "rail_type",
    ]
    
    # Convert Pydantic model to dict for easier access
    transfer_dict = transfer_data.model_dump()
    
    for r in required:
        if r not in transfer_dict or transfer_dict.get(r) in (None, ""):
            raise HTTPException(status_code=400, detail=f"Missing required field: {r}")
        
    print("Received transfer request:", transfer_dict)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not configured in environment variables")
        raise HTTPException(status_code=503, detail="Database not configured")

    sender_master_rtn = transfer_dict.get("sender_master_account_rtn")
    receiver_master_rtn = transfer_dict.get("receiver_master_account_rtn")
    amount_cents = transfer_dict.get("amount_cents")
    rail_type = transfer_dict.get("rail_type")
    external_ref_id = transfer_dict.get("external_ref_id")
    effective_date = transfer_dict.get("effective_date", datetime.datetime.utcnow().date().isoformat())

    try:
        amount_value = float(amount_cents)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount_cents must be numeric")

    if amount_value <= 0:
        raise HTTPException(status_code=400, detail="amount_cents must be greater than 0")

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        normalized_rail = str(rail_type).upper()
        two_leg_rails = {"ACH", "FEDNOW"}

        cur.execute(
            """
            SELECT master_account_rtn
            FROM bank_details
            WHERE master_account_rtn IN (%s, %s)
            """,
            (sender_master_rtn, receiver_master_rtn),
        )
        registered_accounts = {row["master_account_rtn"] for row in cur.fetchall()}
        sender_registered = sender_master_rtn in registered_accounts
        receiver_registered = receiver_master_rtn in registered_accounts

        if normalized_rail in two_leg_rails:
            if not sender_registered or not receiver_registered:
                raise HTTPException(
                    status_code=400,
                    detail="For ACH/FedNow, both sender and receiver must be registered banks",
                )

            cur.execute(
                """
                INSERT INTO central_ledger_entries (master_account_rtn, activity_source_rtn, amount_cents, rail_type, external_ref_id, effective_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    receiver_master_rtn,
                    sender_master_rtn,
                    amount_value,
                    rail_type,
                    external_ref_id,
                    effective_date,
                ),
            )
            credit_entry = cur.fetchone()

            cur.execute(
                """
                INSERT INTO central_ledger_entries (master_account_rtn, activity_source_rtn, amount_cents, rail_type, external_ref_id, effective_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    sender_master_rtn,
                    receiver_master_rtn,
                    -amount_value,
                    rail_type,
                    external_ref_id,
                    effective_date,
                ),
            )
            debit_entry = cur.fetchone()

            cur.execute(
                """
                INSERT INTO running_balance (master_account_rtn, current_running_balance, last_updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (master_account_rtn) DO UPDATE
                  SET current_running_balance = running_balance.current_running_balance + EXCLUDED.current_running_balance,
                      last_updated_at = NOW()
                """,
                (receiver_master_rtn, amount_value),
            )

            cur.execute(
                """
                INSERT INTO running_balance (master_account_rtn, current_running_balance, last_updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (master_account_rtn) DO UPDATE
                  SET current_running_balance = running_balance.current_running_balance + EXCLUDED.current_running_balance,
                      last_updated_at = NOW()
                """,
                (sender_master_rtn, -amount_value),
            )

            response_payload = {
                "mode": "two_leg",
                "entries": {
                    "credit": credit_entry,
                    "debit": debit_entry,
                },
                "amount": amount_value,
                "balances_applied": {
                    "receiver_master_account_rtn": receiver_master_rtn,
                    "sender_master_account_rtn": sender_master_rtn,
                },
            }
        else:
            if sender_registered and receiver_registered:
                raise HTTPException(
                    status_code=400,
                    detail="For non-ACH/FedNow rails, transfer must be between one registered bank and one outside bank",
                )
            if (not sender_registered) and (not receiver_registered):
                raise HTTPException(
                    status_code=400,
                    detail="For non-ACH/FedNow rails, one side must be a registered bank",
                )
            if sender_registered:
                master_rtn = sender_master_rtn
                activity_rtn = receiver_master_rtn
                balance_delta = -amount_value
            else:
                master_rtn = receiver_master_rtn
                activity_rtn = sender_master_rtn
                balance_delta = amount_value

            cur.execute(
                """
                INSERT INTO central_ledger_entries (master_account_rtn, activity_source_rtn, amount_cents, rail_type, external_ref_id, effective_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    master_rtn,
                    activity_rtn,
                    balance_delta,
                    rail_type,
                    external_ref_id,
                    effective_date,
                ),
            )
            single_entry = cur.fetchone()

            cur.execute(
                """
                INSERT INTO running_balance (master_account_rtn, current_running_balance, last_updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (master_account_rtn) DO UPDATE
                  SET current_running_balance = running_balance.current_running_balance + EXCLUDED.current_running_balance,
                      last_updated_at = NOW()
                """,
                (master_rtn, balance_delta),
            )

            response_payload = {
                "mode": "single_leg",
                "entry": single_entry,
                "amount": amount_value,
                "balance_applied": {
                    "master_account_rtn": master_rtn,
                    "delta": balance_delta,
                },
            }

        conn.commit()
        cur.close()
        conn.close()

        print("Transfer successful:", response_payload)

        return response_payload
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
 
def process_pacs008_file(contents: bytes, root) -> pacs008Message:
    msg_id = root.find(".//{*}GrpHdr/{*}MsgId").text
    cdtr_rtn = root.find(".//{*}CdtTrfTxInf/{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId").text
    dbtr_rtn = root.find(".//{*}CdtTrfTxInf/{*}DbtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId").text
    amount = root.find(".//{*}CdtTrfTxInf/{*}IntrBkSttlmAmt").text
    end_to_end_id = root.find(".//{*}CdtTrfTxInf/{*}PmtId/{*}EndToEndId").text
    return pacs008Message(msg_id=msg_id, dbtr_rtn=dbtr_rtn, cdtr_rtn=cdtr_rtn, amount=float(amount), end_to_end_id=end_to_end_id, file_content=contents)

def process_pacs002_file(contents: bytes, root) -> pacs002Message:
    msg_id = root.find(".//{*}GrpHdr/{*}MsgId").text
    dbtr_rtn = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}DbtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId").text
    cdtr_rtn = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId").text
    amount = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}IntrBkSttlmAmt").text
    status = root.find(".//{*}TxInfAndSts/{*}TxSts").text
    end_to_end_id = root.find(".//{*}TxInfAndSts/{*}OrgnlEndToEndId").text
    return pacs002Message(msg_id=msg_id, dbtr_rtn=dbtr_rtn, cdtr_rtn=cdtr_rtn, amount=float(amount), status=status, end_to_end_id=end_to_end_id, file_content=contents)

def process_pain013_file(contents: bytes, root) -> pain013Message:
    msg_id = root.find(".//{*}GrpHdr/{*}MsgId").text
    dbtr_rtn = root.find(".//{*}DbtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId").text
    cdtr_rtn = root.find(".//{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId").text
    amount = root.find(".//{*}InstdAmt").text
    end_to_end_id = root.find(".//{*}PmtId/{*}EndToEndId").text
    return pain013Message(msg_id=msg_id, dbtr_rtn=dbtr_rtn, cdtr_rtn=cdtr_rtn, amount=float(amount), end_to_end_id=end_to_end_id, file_content=contents)

def process_pain014_file(contents: bytes, root) -> pain014Message:
    msg_id = root.find(".//{*}GrpHdr/{*}MsgId").text
    end_to_end_id = root.find(".//{*}TxInfAndSts/{*}OrgnlEndToEndId").text
    status = root.find(".//{*}TxInfAndSts/{*}TxSts").text
    return pain014Message(msg_id=msg_id, status=status, end_to_end_id=end_to_end_id, file_content=contents)

def get_message_object(contents: bytes, filename: str) -> Optional[Union[pacs008Message, pacs002Message, pain013Message, pain014Message]]:
    try:
        if not filename.endswith(".xml"):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")
            
        tree = etree.parse(BytesIO(contents))
        root = tree.getroot()
        if root.tag.endswith("Document"):
            ns = root.nsmap.get(None)  # Get default namespace
            if ns == "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08":
                return process_pacs008_file(contents, root)
            elif ns == "urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10":
                return process_pacs002_file(contents, root)
            elif ns == "urn:iso:std:iso:20022:tech:xsd:pain.013.001.07":
                return process_pain013_file(contents, root)
            elif ns == "urn:iso:std:iso:20022:tech:xsd:pain.014.001.07":
                return process_pain014_file(contents, root)
            else:
                raise HTTPException(status_code=400, detail="Unknown XML namespace")
        else:
            raise HTTPException(status_code=400, detail="Root element must be Document")
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"XML syntax error: {str(exc)}")

def _process_pacs008_message(message: pacs008Message):
    # Check if there is already a pending message with that end-to-end ID in pending_messages. If so, that means the message was a payment request and has it's end-to-end similar to that of pain.014.
    end_to_end_id = message.end_to_end_id

    # Check if it's not already in completed messages to prevent duplicates
    for completed in completed_messages:
        if completed.endToEndId == end_to_end_id:
            if DEBUG:
                print(f"Duplicate pacs.008 message received with EndToEndId: {end_to_end_id}. Ignoring this message since a payment with this EndToEndId has already been completed.")
            raise HTTPException(status_code=400, detail=f"Duplicate pacs.008 message with EndToEndId {end_to_end_id} has already been completed")

    for pending in pending_messages:
        if pending.endToEndId == end_to_end_id:
            # Match, this means the pacs.008 is related to a pain.014. Update the pending messages by adding the pacs.008 file, and just forward it to the receiving bank.
            pending.pacs008_file = message
            _send_file_to_bank_receive_endpoint(
                bank_rtn=message.cdtr_rtn,
                source_filename=f"pacs008_{message.msg_id}.xml",
                contents=message.file_content,
            )
            return
        
    # If no match was found, assume this is a new pacs.008 and add it to pending messages.
    message_obj = messageQueueObj(
        timestamp=datetime.datetime.utcnow().isoformat(),
        status="PDNG",
        endToEndId=message.end_to_end_id,
        dbtr_rtn=message.dbtr_rtn,
        cdtr_rtn=message.cdtr_rtn,
        amount=message.amount,
        interested_parties=[],
        pacs008_file=message
    )
    pending_messages.append(message_obj)

    # Lastly forward the pacs.008 to the receiving bank's endpoint.
    _send_file_to_bank_receive_endpoint(
        bank_rtn=message.cdtr_rtn,
        source_filename=f"pacs008_{message.msg_id}.xml",
        contents=message.file_content,
    )

def _process_pacs002_message(message: pacs002Message):
    end_to_end_id = message.end_to_end_id

    if DEBUG:
        print(f"Processing pacs.002 message with EndToEndId: {end_to_end_id}, Status: {message.status}")

    for pending in pending_messages:
        if pending.endToEndId == end_to_end_id:
            # Pacs.002 should always have a match since it's related to pacs.008
            pending.pacs002_file = message

            if message.status in ("RJCT", "CANC", "BLCK"):
                pending.status = "RJCT" if message.status in ("RJCT", "CANC") else "BLCK"
                # Move it to completed messages if rejected or cancelled
                completed_messages.append(pending)
                pending_messages.remove(pending)
                
                _send_file_to_bank_receive_endpoint(
                    bank_rtn=message.dbtr_rtn,
                    source_filename=f"pacs002_{message.msg_id}.xml",
                    contents=message.file_content,
                )

                _send_file_to_bank_receive_endpoint(
                    bank_rtn=message.cdtr_rtn,
                    source_filename=f"pacs002_{message.msg_id}.xml",
                    contents=message.file_content,
                )
                
                for party in pending.interested_parties:
                    _send_file_to_bank_receive_endpoint(
                        bank_rtn=None,
                        source_filename=f"pacs002_{message.msg_id}.xml",
                        contents=message.file_content,
                        interested_party=party
                    )
                
                return
            
            if message.status in ("ACTC", "ACCP"):
                # Check if debtor has enough balace. Current balance returns as cents, but amount is float dollars.
                current_dbtr_balance = current_balance(message.dbtr_rtn).get("current_balance", 0) / 100 if current_balance(message.dbtr_rtn) is not None else None
                if current_dbtr_balance is None or current_dbtr_balance < message.amount:
                    # If not enough balance, we can choose to either reject the transaction or just let it go through and have negative balance. For this implementation, we'll reject the transaction.
                    pending.status = "RJCT"
                    completed_messages.append(pending)
                    pending_messages.remove(pending)

                    # Change the status and msg id in xml before sending to banks and interested parties
                    root = etree.fromstring(message.file_content)
                    ns = root.nsmap.get(None)
                    etree.register_namespace("", ns)
                    for tx_inf in root.findall(f".//{{{ns}}}TxInfAndSts"):
                        tx_sts = tx_inf.find(f"{{{ns}}}TxSts")
                        if tx_sts is not None:
                            tx_sts.text = "RJCT"

                    # change msg id to indicate it's a rejection message
                    grp_hdr = root.find(f".//{{{ns}}}GrpHdr")
                    if grp_hdr is not None:
                        msg_id = grp_hdr.find(f"{{{ns}}}MsgId")
                        if msg_id is not None:
                            msg_id.text = f"{msg_id.text}_RJCT_INSUFFICIENT_FUNDS"
                    
                    new_file_content = etree.tostring(root)
                    message.file_content = new_file_content  # Update the message content with the modified XML

                    _send_file_to_bank_receive_endpoint(
                        bank_rtn=message.dbtr_rtn,
                        source_filename=f"pacs002_{message.msg_id}.xml",
                        contents=message.file_content,
                    )

                    _send_file_to_bank_receive_endpoint(
                        bank_rtn=message.cdtr_rtn,
                        source_filename=f"pacs002_{message.msg_id}.xml",
                        contents=message.file_content,
                    )

                    for party in pending.interested_parties:
                        _send_file_to_bank_receive_endpoint(
                            bank_rtn=None,
                            source_filename=f"pacs002_{message.msg_id}.xml",
                            contents=message.file_content,
                            interested_party=party
                        )
                    
                    return
                
                # If enough balance, trnasfer the funds.
                transfer_response = transfer_funds(
                    sending_bank_rtn=message.dbtr_rtn,
                    receiving_bank_rtn=message.cdtr_rtn,
                    amount_cents=message.amount * 100,  # Convert dollars to cents
                    rail_type="FedNow",
                    external_ref_id=message.end_to_end_id                
                )

                if transfer_response is None:

                    if DEBUG:
                        print(f"Transfer failed for EndToEndId: {message.end_to_end_id}. Rejecting the transaction.")

                    pending.status = "RJCT"
                    completed_messages.append(pending)
                    pending_messages.remove(pending)

                    # Change the status and msg id in xml before sending to banks and interested parties
                    root = etree.fromstring(message.file_content)
                    ns = root.nsmap.get(None)
                    etree.register_namespace("", ns)
                    for tx_inf in root.findall(f".//{{{ns}}}TxInfAndSts"):
                        tx_sts = tx_inf.find(f"{{{ns}}}TxSts")
                        if tx_sts is not None:
                            tx_sts.text = "RJCT"

                    # change msg id to indicate it's a rejection message
                    grp_hdr = root.find(f".//{{{ns}}}GrpHdr")
                    if grp_hdr is not None:
                        msg_id = grp_hdr.find(f"{{{ns}}}MsgId")
                        if msg_id is not None:
                            msg_id.text = f"{msg_id.text}_RJCT_INSUFFICIENT_FUNDS"
                    
                    new_file_content = etree.tostring(root)
                    message.file_content = new_file_content  # Update the message content with the modified XML

                    _send_file_to_bank_receive_endpoint(
                        bank_rtn=message.dbtr_rtn,
                        source_filename=f"pacs002_{message.msg_id}.xml",
                        contents=message.file_content,
                    )

                    _send_file_to_bank_receive_endpoint(
                        bank_rtn=message.cdtr_rtn,
                        source_filename=f"pacs002_{message.msg_id}.xml",
                        contents=message.file_content,
                    )

                    for party in pending.interested_parties:
                        _send_file_to_bank_receive_endpoint(
                            bank_rtn=None,
                            source_filename=f"pacs002_{message.msg_id}.xml",
                            contents=message.file_content,
                            interested_party=party
                        )
                    
                    return
                
                # If transfer was successful, update the status to ACCP, add new msg id and move to completed messages

                pending.status = "ACCP"
                completed_messages.append(pending)
                pending_messages.remove(pending)
                # Change the msg id in xml to indicate it's an acceptance message
                root = etree.fromstring(message.file_content)
                msg_id = root.find(".//{*}MsgId")
                if msg_id is not None:
                    msg_id.text = f"{msg_id.text}_ACCP"
                new_file_content = etree.tostring(root)
                message.file_content = new_file_content  # Update the message content with the modified XML

                _send_file_to_bank_receive_endpoint(
                    bank_rtn=message.dbtr_rtn,
                    source_filename=f"pacs002_{message.msg_id}.xml",
                    contents=message.file_content,
                )

                _send_file_to_bank_receive_endpoint(
                    bank_rtn=message.cdtr_rtn,
                    source_filename=f"pacs002_{message.msg_id}.xml",
                    contents=message.file_content,
                )

                for party in pending.interested_parties:
                    _send_file_to_bank_receive_endpoint(
                        bank_rtn=None,
                        source_filename=f"pacs002_{message.msg_id}.xml",
                        contents=message.file_content,
                        interested_party=party
                    )
            return
        else:
            if DEBUG:
                print(f"No matching pending message found for pacs.002 with EndToEndId: {end_to_end_id}. pacs.002 should always be related to a pacs.008. Ignoring this message.")
            raise HTTPException(status_code=400, detail=f"No matching pending message found for pacs.002 with EndToEndId: {end_to_end_id}. pacs.002 should always be related to a pacs.008.")
        
    for completed in completed_messages:
        if completed.endToEndId == end_to_end_id:
            # if found in completed, this might be a duplicate pacs.002 or message was rejected by pain.014
            if DEBUG:
                print(f"Duplicate pacs.002 message received with EndToEndId: {end_to_end_id}. Ignoring this message since a payment with this EndToEndId has already been completed.")
            raise HTTPException(status_code=400, detail=f"Duplicate pacs.002 message with EndToEndId {end_to_end_id} has already been completed")
    
    # if no match was found in pending or completed, this is unexpected since pacs.002 should always be related to a pacs.008
    if DEBUG:
        print(f"No matching pending or completed message found for pacs.002 with EndToEndId: {end_to_end_id}. pacs.002 should always be related to a pacs.008. Ignoring this message.")
    raise HTTPException(status_code=400, detail=f"No matching pending or completed message found for pacs.002 with EndToEndId: {end_to_end_id}. pacs.002 should always be related to a pacs.008.")

def _process_pain013_message(message: pain013Message, sender_port: Optional[str] = None):
    # Check pending messages for matching end to end id to prevent duplicates
    for pending in pending_messages:
        if pending.endToEndId == message.end_to_end_id:
            if DEBUG:
                print(f"Duplicate pain.013 message received with EndToEndId: {message.end_to_end_id}. Ignoring this message since it's already being processed.")
            raise HTTPException(status_code=400, detail=f"Duplicate pain.013 message with EndToEndId {message.end_to_end_id} is already being processed")

    for completed in completed_messages:
        if completed.endToEndId == message.end_to_end_id:
            if DEBUG:
                print(f"Duplicate pain.013 message received with EndToEndId: {message.end_to_end_id}. Ignoring this message since a payment with this EndToEndId has already been completed.")
            raise HTTPException(status_code=400, detail=f"Duplicate pain.013 message with EndToEndId {message.end_to_end_id} has already been completed")

    # Create messageQueueObj and send it to the appropriate MQ based on the debtor rtn.
    message_obj = messageQueueObj(
        timestamp=datetime.datetime.utcnow().isoformat(),
        status="PDNG",
        endToEndId=message.end_to_end_id,
        dbtr_rtn=message.dbtr_rtn if hasattr(message, 'dbtr_rtn') else None,
        cdtr_rtn=message.cdtr_rtn if hasattr(message, 'cdtr_rtn') else None,
        amount=message.amount if hasattr(message, 'amount') else None,
        interested_parties= [port_to_name_map.get(sender_port)] if sender_port else [],  # Add sender port to interested parties for pain.013 messages
        pain013_file=message
    )

    # Append to pending_messages
    pending_messages.append(message_obj)

    # Forward to the appropriate MQ based on debtor rtn
    target_bank_rtn = message.dbtr_rtn if hasattr(message, 'dbtr_rtn') else None
    if target_bank_rtn:
        _send_file_to_bank_receive_endpoint(
            bank_rtn=target_bank_rtn,
            source_filename=f"pain013_{message.msg_id}.xml",
            contents=message.file_content,
        )

def _process_pain014_message(message: pain014Message):
    # Check if message is in pending messages and send it to interested parties from that messageQueueObj.
    interested_parties = []
    for pending in pending_messages:
        if pending.endToEndId == message.end_to_end_id:
            interested_parties = pending.interested_parties
            pending.pain014_file = message
            if message.status in ("RJCT", "CANC"):
                pending.status = "RJCT"
                # Move it to completed messages if rejected or cancelled
                completed_messages.append(pending)
                pending_messages.remove(pending)
            break
    for completed in completed_messages:
        if completed.endToEndId == message.end_to_end_id:
            interested_parties = completed.interested_parties
            completed.pain014_file = message
            if message.status in ("RJCT", "CANC", "BLCK"):
                completed.status = "RJCT" if message.status in ("RJCT", "CANC") else "BLCK"
            break

    if DEBUG:
        print(f"Processing pain.014 for EndToEndId: {message.end_to_end_id}, found interested parties: {interested_parties}, status: {message.status}")
    
    # Forward the pain.014 message to all interested parties
    for party in interested_parties:
        _send_file_to_bank_receive_endpoint(
            bank_rtn=None,
            source_filename=f"pain014_{message.msg_id}.xml",
            contents=message.file_content,
            interested_party=party
        )
    
    if interested_parties == []:
        if DEBUG:
            print(f"No interested parties found for pain.014 message with EndToEndId: {message.end_to_end_id}.")
        raise HTTPException(status_code=400, detail=f"No interested parties found for pain.014 message with EndToEndId: {message.end_to_end_id}. EndToEndId should match that of a pain.013 message.")

def process_file(contents: bytes, filename: str, sender_port: Optional[str] = None):
    message_obj = get_message_object(contents, filename)

    if isinstance(message_obj, pacs008Message):
        if DEBUG:
            print("Processed pacs.008 message:")
            print(message_obj)
        
        _process_pacs008_message(message_obj)

    if isinstance(message_obj, pacs002Message):
        if DEBUG:
            print("Processed pacs.002 message:")
            print(message_obj)

        _process_pacs002_message(message_obj)

    if isinstance(message_obj, pain013Message):
        if DEBUG:
            print("Processed pain.013 message:")
            print(message_obj)

        _process_pain013_message(message_obj, sender_port)

    if isinstance(message_obj, pain014Message):
        if DEBUG:
            print("Processed pain.014 message:")
            print(message_obj)

        _process_pain014_message(message_obj)

    if DEBUG:
        print("Current pending messages in system:")
        for msg in pending_messages:
            print(f"Timestamp: {msg.timestamp}, Status: {msg.status}, EndToEndId: {msg.endToEndId}, Debtor RTN: {msg.dbtr_rtn}, Creditor RTN: {msg.cdtr_rtn}, Amount: {msg.amount}, Interested Parties: {msg.interested_parties}")

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

def _send_file_to_bank_receive_endpoint(contents: bytes, bank_rtn: str = None, source_filename: str = "message.xml", interested_party: str = None) -> dict:
    if not bank_rtn and not interested_party:
        raise HTTPException(status_code=400, detail="Missing target bank routing number")

    if bank_rtn:
        if DEBUG:
            print(f"Sending file to bank with RTN: {bank_rtn}, source filename: {source_filename}, url from bank map: {banks_ports_map.get(bank_rtn, MQ_BANK0_URL)}")
        endpoint_base = banks_ports_map.get(bank_rtn, None)
        if endpoint_base is None:
            raise HTTPException(status_code=400, detail=f"Bank RTN {bank_rtn} not found in bank map")
        if not endpoint_base.startswith(("http://", "https://")):
            endpoint_base = f"http://{endpoint_base}"

    if interested_party:
        if DEBUG:
            print(f"Sending file to interested party: {interested_party}, source filename: {source_filename}, url from bank map: {banks_ports_map.get(interested_party, MQ_BANK0_URL)}")
        endpoint_base = banks_ports_map.get(interested_party, None)
        if endpoint_base is None:
            raise HTTPException(status_code=400, detail=f"Interested party {interested_party} not found in bank map")
        if not endpoint_base.startswith(("http://", "https://")):
            endpoint_base = f"http://{endpoint_base}"

    upload_filename = f"{bank_rtn}_message_{uuid.uuid4().hex}_{os.path.basename(source_filename)}"
    body, boundary = _build_multipart_file_body("file", upload_filename, contents)
    target_url = endpoint_base.rstrip("/") + "/receive"

    req = request.Request(target_url, method="POST", data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with request.urlopen(req) as response:
            response_body = response.read().decode("utf-8")
            return {
                "status": "sent",
                "bank_rtn": bank_rtn if bank_rtn else "",
                "target_url": target_url,
                "response": response_body,
                "filename": upload_filename,
                "size_bytes": len(contents),
            }
    except error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=f"Failed to send message to bank {bank_rtn if bank_rtn else interested_party if interested_party else 'Unknown'}: {exc.reason}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error sending message to bank {bank_rtn}: {str(exc)}")

@fednow.post("/send-message", tags=["Messages"])
def send_message(bank_rtn: str, file: UploadFile = File(...), interested_parties: Optional[List[str]] = None):
    """Send an uploaded XML file to the target bank /receive endpoint as multipart form-data."""
    if not file.filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="File must be XML (.xml)")

    contents = file.file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if bank_rtn:
        return _send_file_to_bank_receive_endpoint(
            bank_rtn=bank_rtn,
            source_filename=file.filename,
            contents=contents,
            interested_party=None
        )
    if interested_parties:
        for party in interested_parties:
            _send_file_to_bank_receive_endpoint(
                bank_rtn=None,
                source_filename=file.filename,
                contents=contents,
                interested_party=party
            )
        return {
            "status": "sent to interested parties",
            "filename": file.filename,
            "size_bytes": len(contents),
            "interested_parties": interested_parties,
        }

def current_balance(master_account_rtn: str):
    """Get the precise current balance for a master account RTN.

    This endpoint uses `central_ledger_entries` (source of truth), not
    `running_balance`.
    """
    if not master_account_rtn:
        raise HTTPException(status_code=400, detail="master_account_rtn is required")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        conn = psycopg2.connect(db_url, connect_timeout=5)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            SELECT master_account_rtn, legal_name
            FROM bank_details
            WHERE master_account_rtn = %s
            """,
            (master_account_rtn,),
        )
        bank_row = cur.fetchone()
        if not bank_row:
            raise HTTPException(status_code=404, detail="master_account_rtn not found")

        cur.execute(
            """
            SELECT
              COALESCE(SUM(amount_cents), 0) AS current_balance,
              COALESCE(SUM(CASE WHEN amount_cents > 0 THEN amount_cents ELSE 0 END), 0) AS total_credits,
              COALESCE(SUM(CASE WHEN amount_cents < 0 THEN -amount_cents ELSE 0 END), 0) AS total_debits,
              COUNT(*) AS ledger_entry_count,
              MAX(effective_date) AS latest_effective_date
            FROM central_ledger_entries
            WHERE master_account_rtn = %s
            """,
            (master_account_rtn,),
        )
        ledger_totals = cur.fetchone()

        cur.close()
        conn.close()

        return {
            "master_account_rtn": bank_row["master_account_rtn"],
            "legal_name": bank_row["legal_name"],
            "current_balance": ledger_totals["current_balance"],
            "total_credits": ledger_totals["total_credits"],
            "total_debits": ledger_totals["total_debits"],
            "ledger_entry_count": ledger_totals["ledger_entry_count"],
            "latest_effective_date": ledger_totals["latest_effective_date"],
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.exception("Failed to calculate current balance: %s", e)
        raise HTTPException(status_code=500, detail=str(e))