import datetime
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, UploadFile, File
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

banks_ports_map = {
    MQ_BANK0_RTN: MQ_BANK0_URL,
    MQ_BANK1_RTN: MQ_BANK1_URL,
    MQ_BANK2_RTN: MQ_BANK2_URL,
    MQ_BANK3_RTN: MQ_BANK3_URL,
    MQ_BANK4_RTN: MQ_BANK4_URL,
    MQ_BANK5_RTN: MQ_BANK5_URL,
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
        {"routing_number": MQ_BANK5_RTN, "legal_name": MQ_BANK5_LEGAL_NAME, "port": MQ_BANK5_PORT}
    ]

@fednow.post("/collect", tags=["Messages"])
def collect_message(file: UploadFile = File(...)):
    """Save an uploaded XML file into the collected directory after formal validation."""
    try:
        if not file.filename.lower().endswith(".xml"):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")

        contents = file.file.read()

        validation_status = validate_xml(contents, file.filename)

        filepath = os.path.join("collected", file.filename)
        with open(filepath, "wb") as handle:
            handle.write(contents)

        processed_content = process_file(contents, file.filename)
        if processed_content is None:
            raise HTTPException(status_code=400, detail="Unsupported XML structure for processing")

        if processed_content.get("type") == "pacs.008":
            # Send to receiving bank
            target_bank_rtn = processed_content.get("cdtr_rtn")
            _send_file_to_bank_receive_endpoint(
                bank_rtn=target_bank_rtn,
                source_filename=file.filename,
                contents=contents,
            )
        elif processed_content.get("type") == "pacs.002":
            # Send to sending bank
            content = processed_content
            target_bank_rtn = content.get("dbtr_rtn")
            creditor_bank_rtn = content.get("cdtr_rtn")
            if content.get("status") != "ACCP":
                _send_file_to_bank_receive_endpoint(
                    bank_rtn=target_bank_rtn,
                    source_filename=file.filename,
                    contents=contents,
                )
            
            if content.get("status") == "ACCP":
                # If the status is accepted, we can also trigger a funds transfer in our system
                amount = content.get("amount")
                transfer_funds(
                    sending_bank_rtn=target_bank_rtn,
                    receiving_bank_rtn=creditor_bank_rtn,
                    amount_cents=float(amount) * 100,  # Convert to cents
                    rail_type="FedNow",
                    external_ref_id=content.get("msg_id"),
                )
                _send_file_to_bank_receive_endpoint(
                    bank_rtn=target_bank_rtn,
                    source_filename=file.filename,
                    contents=contents,
                )

        return {
            "status": "received and sent",
            "filename": file.filename,
            "size_bytes": len(contents),
            "validation": validation_status,
        }
    except HTTPException:
        raise
    except Exception as exc:
        details = str(exc) + (f"Creditor rtn: {processed_content.get('cdtr_rtn')}, Debtor rtn: {processed_content.get('dbtr_rtn')}" if 'processed_content' in locals() else "")
        raise HTTPException(status_code=500, detail=details)

def validate_xml(contents: bytes, filename: str) -> str:
    # If <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08"> check if:
    # <FIToFICstmrCdtTrf>
    #   <GrpHdr>
    #       <MsgId>MSG-20260526-0001</MsgId>
    #   </GrpHdr>
    # </FIToFICstmrCdtTrf>
    # </Document>
    # and if 
    # <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
    #     <FIToFICstmrCdtTrf>
    #     <CdtTrfTxInf>
    #         <CdtrAgt>
    #             <FinInstnId>
    #             <ClrSysMmbId>
    #                 <MmbId>040104018</MmbId> <!-- Receiving Banks RTN -->
    #             </ClrSysMmbId>
    #             </FinInstnId>
    #         </CdtrAgt>
    #     </CdtTrfTxInf>
    #     </FIToFICstmrCdtTrf>
    # </Document>
    # and 
    # <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
    #     <FIToFICstmrCdtTrf>
    #         <CdtTrfTxInf>
    #             <IntrBkSttlmAmt Ccy="USD">1500.50</IntrBkSttlmAmt>
    #         </CdtTrfTxInf>
    #     </FIToFICstmrCdtTrf>
    # </Document>
    #
    # or if it's pacs.002 then check:
    # <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10">
	# <FIToFIPmtStsRpt>
	# 	<GrpHdr>
	# 		<MsgId>MSG-20260526-0001-STS-0001</MsgId> <!-- Unique to every message -->
    #     </GrpHdr>
    # </FIToFIPmtStsRpt>
    # </Document>
    # and 
    # <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10">
    #     <FIToFIPmtStsRpt>
    #         <TxInfAndSts>
    #             <TxSts>ACCP</TxSts>
    #             <OrgnlTxRef>
    #                 <DbtrAgt>
    #                     <FinInstnId>
    #                         <ClrSysMmbId>
    #                             <MmbId>040104018</MmbId> <!-- Sending Bank's RTN -->
    #                         </ClrSysMmbId>
    #                     </FinInstnId>
    #                 </DbtrAgt>
    #            </OrgnlTxRef>
    #         </TxInfAndSts>
    #     </FIToFIPmtStsRpt>
    # </Document>
    # and 
    # <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10">
	#   <FIToFIPmtStsRpt>
    #         <OrgnlGrpInfAndSts>
    #             <GrpSts>ACCP</GrpSts> <!-- Status of the entire group of transactions can be: ACCP (Accepted), RJCT (Rejected), PDNG (Pending), BLCK (Blocked), ACTC (Accepted technical validation successful) -->
    #         </OrgnlGrpInfAndSts>
    #     </FIToFIPmtStsRpt>
    # </Document>
    # and 
    # <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10">
    #     <FIToFIPmtStsRpt>
    #         <TxInfAndSts>
    #             <TxSts>ACCP</TxSts>
    #         <OrgnlTxRef>
    #             <IntrBkSttlmAmt Ccy="USD">1500.50</IntrBkSttlmAmt>
    #         </OrgnlTxRef>
    #         </TxInfAndSts>
    #     </FIToFIPmtStsRpt>
    # </Document>

    try:
        if not filename.endswith(".xml"):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")

        tree = etree.parse(BytesIO(contents))
        root = tree.getroot()
        if root.tag.endswith("Document"):
            ns = root.nsmap.get(None)  # Get default namespace
            if ns == "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08":
                # Validate pacs.008 structure
                msg_id = root.find(".//{*}GrpHdr/{*}MsgId")
                cdtr_rtn = root.find(".//{*}CdtTrfTxInf/{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
                dbtr_rtn = root.find(".//{*}CdtTrfTxInf/{*}DbtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
                amount = root.find(".//{*}CdtTrfTxInf/{*}IntrBkSttlmAmt")

                # check if both rtns are registered banks
                if cdtr_rtn is not None and cdtr_rtn.text not in banks_ports_map:
                    raise HTTPException(status_code=400, detail=f"Unknown cdtr bank RTN: {cdtr_rtn.text}")
                if dbtr_rtn is not None and dbtr_rtn.text not in banks_ports_map:
                    raise HTTPException(status_code=400, detail=f"Unknown dbtr bank RTN: {dbtr_rtn.text}")

                if msg_id is None or cdtr_rtn is None or dbtr_rtn is None or amount is None:
                    raise HTTPException(status_code=400, detail="Invalid pacs.008 structure")
                return "Valid pacs.008"
            elif ns == "urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10":
                # Validate pacs.002 structure
                msg_id = root.find(".//{*}GrpHdr/{*}MsgId")
                dbtr_rtn = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}DbtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
                cdtr_rtn = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId")
                amount = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}IntrBkSttlmAmt")
                status = root.find(".//{*}TxInfAndSts/{*}TxSts")

                # check if both rtns are registered banks
                if cdtr_rtn is not None and cdtr_rtn.text not in banks_ports_map:
                    raise HTTPException(status_code=400, detail=f"Unknown cdtr bank RTN: {cdtr_rtn.text}")
                if dbtr_rtn is not None and dbtr_rtn.text not in banks_ports_map:
                    raise HTTPException(status_code=400, detail=f"Unknown dbtr bank RTN: {dbtr_rtn.text}")

                if msg_id is None or dbtr_rtn is None or amount is None or status is None:
                    raise HTTPException(status_code=400, detail="Invalid pacs.002 structure")
                return "Valid pacs.002"
            else:
                raise HTTPException(status_code=400, detail="Unknown XML namespace")
        else:
            raise HTTPException(status_code=400, detail="Root element must be Document")
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"XML syntax error: {str(exc)}")
    
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


class FundsTransferRequest(BaseModel):
    sender_master_account_rtn: str
    receiver_master_account_rtn: str
    amount_cents: float
    rail_type: str
    external_ref_id: Optional[str] = None
    effective_date: Optional[str] = None

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

    
def process_file(contents: bytes, filename: str):
    # If the file is pacs.008 then extract the following fields:
    # <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
    #     <FIToFICstmrCdtTrf>
    #     <CdtTrfTxInf>
    #         <CdtrAgt>
    #             <FinInstnId>
    #             <ClrSysMmbId>
    #                 <MmbId>040104018</MmbId> <!-- Receiving Banks RTN -->
    #             </ClrSysMmbId>
    #             </FinInstnId>
    #         </CdtrAgt>
    #     </CdtTrfTxInf>
    #     </FIToFICstmrCdtTrf>
    # </Document>
    # and if it's pacs.002 then extract:
    # <Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10">
    #     <FIToFIPmtStsRpt>
    #         <TxInfAndSts>
    #             <TxSts>ACCP</TxSts>
    #             <OrgnlTxRef>
    #                 <DbtrAgt>
    #                     <FinInstnId>
    #                         <ClrSysMmbId>
    #                             <MmbId>040104018</MmbId> <!-- Sending Bank's RTN -->
    #                         </ClrSysMmbId>
    #                     </FinInstnId>
    #                 </DbtrAgt>
    #            </OrgnlTxRef>
    #         </TxInfAndSts>
    #     </FIToFIPmtStsRpt>
    # </Document>
    # After extracting the fields send the file to the appropriate bank endpoint based on the RTN.

    try:
        if not filename.endswith(".xml"):
            raise HTTPException(status_code=400, detail="File must be XML (.xml)")

        tree = etree.parse(BytesIO(contents))
        root = tree.getroot()
        if root.tag.endswith("Document"):
            ns = root.nsmap.get(None)  # Get default namespace
            if ns == "urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08":
                # Extract pacs.008 fields
                msg_id = root.find(".//{*}GrpHdr/{*}MsgId").text
                cdtr_rtn = root.find(".//{*}CdtTrfTxInf/{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId").text
                amount = root.find(".//{*}CdtTrfTxInf/{*}IntrBkSttlmAmt").text
                return {"type": "pacs.008", "msg_id": msg_id, "cdtr_rtn": cdtr_rtn, "amount": amount}
            elif ns == "urn:iso:std:iso:20022:tech:xsd:pacs.002.001.10":
                # Extract pacs.002 fields
                msg_id = root.find(".//{*}GrpHdr/{*}MsgId").text
                dbtr_rtn = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}DbtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId").text
                cdtr_rtn = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}CdtrAgt/{*}FinInstnId/{*}ClrSysMmbId/{*}MmbId").text
                amount = root.find(".//{*}TxInfAndSts/{*}OrgnlTxRef/{*}IntrBkSttlmAmt").text
                status = root.find(".//{*}TxInfAndSts/{*}TxSts").text
                return {"type": "pacs.002", "msg_id": msg_id, "dbtr_rtn": dbtr_rtn, "cdtr_rtn": cdtr_rtn, "amount": amount, "status": status}
            else:
                raise HTTPException(status_code=400, detail="Unknown XML namespace")
        else:
            raise HTTPException(status_code=400, detail="Root element must be Document")
    except etree.XMLSyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"XML syntax error: {str(exc)}")

    
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


def _send_file_to_bank_receive_endpoint(bank_rtn: str, source_filename: str, contents: bytes) -> dict:
    if not bank_rtn:
        raise HTTPException(status_code=400, detail="Missing target bank routing number")

    endpoint_base = banks_ports_map.get(bank_rtn, MQ_BANK0_URL)
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
                "bank_rtn": bank_rtn,
                "target_url": target_url,
                "response": response_body,
                "filename": upload_filename,
                "size_bytes": len(contents),
            }
    except error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=f"Failed to send message to bank {bank_rtn}: {exc.reason}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error sending message to bank {bank_rtn}: {str(exc)}")


@fednow.post("/send-message", tags=["Messages"])
def send_message(bank_rtn: str, file: UploadFile = File(...)):
    """Send an uploaded XML file to the target bank /receive endpoint as multipart form-data."""
    if not file.filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="File must be XML (.xml)")

    contents = file.file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    return _send_file_to_bank_receive_endpoint(
        bank_rtn=bank_rtn,
        source_filename=file.filename,
        contents=contents,
    )
    