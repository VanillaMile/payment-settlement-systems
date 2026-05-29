from fastapi import FastAPI, HTTPException, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os
from typing import Optional
import re
import subprocess
import logging
import shutil
import json
import base64
from datetime import datetime
import time
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from achFileBuilder import *

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load .env if present
load_dotenv()

# --- FRB Configuration ---
FRB_ROUTING_NUMBER = os.environ.get("FRB_ROUTING_NUMBER", "090000515")
FRB_LEGAL_NAME = os.environ.get("FRB_LEGAL_NAME", "Federal Reserve Bank")

logger.info("FRB Configuration: RTN=%s, Legal Name=%s", FRB_ROUTING_NUMBER, FRB_LEGAL_NAME)

collected_dir = "collected"
if not os.path.exists(collected_dir):
    os.makedirs(collected_dir)

archive_dir = "archive"
if not os.path.exists(archive_dir):
    os.makedirs(archive_dir)

# Automated bank configuration on startup variables
BANK0 = os.environ.get("BANK0", "baguette-bank")
BANK1 = os.environ.get("BANK1", "leek-bank")
BANK2 = os.environ.get("BANK2", "bank-of-the-onion")
BANK3 = os.environ.get("BANK3", "croissant-bank")
BANK4 = os.environ.get("BANK4", "donut-bank")
BANK5 = os.environ.get("BANK5", "coffee-bank")

BANK0_RTN = os.environ.get("BANK0_RTN", "040104018")
BANK1_RTN = os.environ.get("BANK1_RTN", "010101012")
BANK2_RTN = os.environ.get("BANK2_RTN", "910310314")
BANK3_RTN = os.environ.get("BANK3_RTN", "514310008")
BANK4_RTN = os.environ.get("BANK4_RTN", "888777885")
BANK5_RTN = os.environ.get("BANK5_RTN", "666777667")

BANK0_MRTN = os.environ.get("BANK0_MRTN", BANK0_RTN)
BANK1_MRTN = os.environ.get("BANK1_MRTN", BANK1_RTN)
BANK2_MRTN = os.environ.get("BANK2_MRTN", BANK2_RTN)
BANK3_MRTN = os.environ.get("BANK3_MRTN", BANK3_RTN)
BANK4_MRTN = os.environ.get("BANK4_MRTN", BANK4_RTN)
BANK5_MRTN = os.environ.get("BANK5_MRTN", BANK5_RTN)

BANK0_LEGAL_NAME = os.environ.get("BANK0_LEGAL_NAME", "Baguette Bank")
BANK1_LEGAL_NAME = os.environ.get("BANK1_LEGAL_NAME", "Leek Bank")
BANK2_LEGAL_NAME = os.environ.get("BANK2_LEGAL_NAME", "Bank of the Onion")
BANK3_LEGAL_NAME = os.environ.get("BANK3_LEGAL_NAME", "Croissant Bank")
BANK4_LEGAL_NAME = os.environ.get("BANK4_LEGAL_NAME", "Donut Bank")
BANK5_LEGAL_NAME = os.environ.get("BANK5_LEGAL_NAME", "Coffee Bank")

BANK0_FEIN = os.environ.get("BANK0_FEIN", "123456789")
BANK1_FEIN = os.environ.get("BANK1_FEIN", "987654321")
BANK2_FEIN = os.environ.get("BANK2_FEIN", "555555555")
BANK3_FEIN = os.environ.get("BANK3_FEIN", "111111111")
BANK4_FEIN = os.environ.get("BANK4_FEIN", "222222222")
BANK5_FEIN = os.environ.get("BANK5_FEIN", "333333333")

BANK0_NET_DEBIT_CAP = int(os.environ.get("BANK0_NET_DEBIT_CAP", "100000000"))
BANK1_NET_DEBIT_CAP = int(os.environ.get("BANK1_NET_DEBIT_CAP", "100000000"))
BANK2_NET_DEBIT_CAP = int(os.environ.get("BANK2_NET_DEBIT_CAP", "100000000"))
BANK3_NET_DEBIT_CAP = int(os.environ.get("BANK3_NET_DEBIT_CAP", "100000000"))
BANK4_NET_DEBIT_CAP = int(os.environ.get("BANK4_NET_DEBIT_CAP", "100000000"))
BANK5_NET_DEBIT_CAP = int(os.environ.get("BANK5_NET_DEBIT_CAP", "100000000"))

BANK0_INITIAL_BALANCE = int(os.environ.get("BANK0_INITIAL_BALANCE", "1000000000"))
BANK1_INITIAL_BALANCE = int(os.environ.get("BANK1_INITIAL_BALANCE", "1000000000"))
BANK2_INITIAL_BALANCE = int(os.environ.get("BANK2_INITIAL_BALANCE", "1000000000"))
BANK3_INITIAL_BALANCE = int(os.environ.get("BANK3_INITIAL_BALANCE", "1000000000"))
BANK4_INITIAL_BALANCE = int(os.environ.get("BANK4_INITIAL_BALANCE", "1000000000"))
BANK5_INITIAL_BALANCE = int(os.environ.get("BANK5_INITIAL_BALANCE", "1000000000"))


def seed_bank_to_database(db_url, bank_config, initial_sender_rtn):
    conn = None
    cur = None
    try:
        max_attempts = int(os.environ.get("AUTOMATED_CONFIG_DB_RETRIES", "30"))
        retry_delay_seconds = float(os.environ.get("AUTOMATED_CONFIG_DB_RETRY_DELAY_SECONDS", "2"))

        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                conn = psycopg2.connect(db_url, connect_timeout=5)
                break
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts:
                    raise
                logger.warning(
                    "Postgres not ready yet for %s (%s); retrying in %ss (%s/%s)",
                    bank_config["sftp_username"],
                    bank_config["primary_routing_transit_number"],
                    retry_delay_seconds,
                    attempt,
                    max_attempts,
                )
                time.sleep(retry_delay_seconds)

        if conn is None:
            raise last_error or RuntimeError("Could not connect to Postgres")

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            SELECT 1
            FROM bank_details
            WHERE primary_routing_transit_number = %s
            """,
            (bank_config["primary_routing_transit_number"],),
        )
        if cur.fetchone() is not None:
            logger.info(
                "Skipping seed for %s (%s) because it already exists",
                bank_config["sftp_username"],
                bank_config["primary_routing_transit_number"],
            )
            return False

        cur.execute(
            """
            INSERT INTO bank_details (
                primary_routing_transit_number,
                legal_name,
                federal_employer_identification_number,
                master_account_rtn,
                net_debit_cap,
                sftp_username,
                server_certificate_expiry
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                bank_config["primary_routing_transit_number"],
                bank_config["legal_name"],
                bank_config["federal_employer_identification_number"],
                bank_config["master_account_rtn"],
                bank_config["net_debit_cap"],
                bank_config["sftp_username"],
                bank_config["server_certificate_expiry"],
            ),
        )

        cur.execute(
            """
            INSERT INTO ach_participants (primary_routing_transit_number, type, restricted)
            VALUES (%s, %s, %s)
            ON CONFLICT (primary_routing_transit_number) DO UPDATE
              SET type = EXCLUDED.type,
                  restricted = EXCLUDED.restricted
            """,
            (
                bank_config["primary_routing_transit_number"],
                "both",
                0,
            ),
        )

        initial_balance = int(bank_config.get("initial_balance", 0) or 0)
        if initial_balance > 0:
            cur.execute("LOCK TABLE central_ledger_entries IN EXCLUSIVE MODE")
            cur.execute("SELECT COALESCE(MAX(entry_id), 0) AS max_id FROM central_ledger_entries")
            next_entry_id = cur.fetchone()["max_id"] + 1

            cur.execute(
                """
                INSERT INTO central_ledger_entries (
                    entry_id,
                    master_account_rtn,
                    activity_source_rtn,
                    amount_cents,
                    rail_type,
                    external_ref_id,
                    effective_date
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    next_entry_id,
                    bank_config["master_account_rtn"],
                    initial_sender_rtn,
                    float(initial_balance),
                    "FedWire",
                    f"INITIAL_BALANCE:{bank_config['sftp_username']}",
                    datetime.utcnow().date().isoformat(),
                ),
            )

            cur.execute(
                """
                INSERT INTO running_balance (master_account_rtn, current_running_balance, last_updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (master_account_rtn) DO UPDATE
                  SET current_running_balance = running_balance.current_running_balance + EXCLUDED.current_running_balance,
                      last_updated_at = NOW()
                """,
                (bank_config["master_account_rtn"], initial_balance),
            )

        conn.commit()
        logger.info(
            "Seeded bank %s (%s) into database",
            bank_config["sftp_username"],
            bank_config["primary_routing_transit_number"],
        )
        return True
    except Exception:
        if conn is not None:
            conn.rollback()
        logger.exception(
            "Failed to seed bank %s into database",
            bank_config.get("sftp_username"),
        )
        return False
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


BANK_SEED_CONFIGS = [
    {
        "primary_routing_transit_number": BANK0_RTN,
        "legal_name": BANK0_LEGAL_NAME,
        "federal_employer_identification_number": BANK0_FEIN,
        "master_account_rtn": BANK0_MRTN,
        "net_debit_cap": BANK0_NET_DEBIT_CAP,
        "sftp_username": BANK0,
        "server_certificate_expiry": None,
        "initial_balance": BANK0_INITIAL_BALANCE,
    },
    {
        "primary_routing_transit_number": BANK1_RTN,
        "legal_name": BANK1_LEGAL_NAME,
        "federal_employer_identification_number": BANK1_FEIN,
        "master_account_rtn": BANK1_MRTN,
        "net_debit_cap": BANK1_NET_DEBIT_CAP,
        "sftp_username": BANK1,
        "server_certificate_expiry": None,
        "initial_balance": BANK1_INITIAL_BALANCE,
    },
    {
        "primary_routing_transit_number": BANK2_RTN,
        "legal_name": BANK2_LEGAL_NAME,
        "federal_employer_identification_number": BANK2_FEIN,
        "master_account_rtn": BANK2_MRTN,
        "net_debit_cap": BANK2_NET_DEBIT_CAP,
        "sftp_username": BANK2,
        "server_certificate_expiry": None,
        "initial_balance": BANK2_INITIAL_BALANCE,
    },
    {
        "primary_routing_transit_number": BANK3_RTN,
        "legal_name": BANK3_LEGAL_NAME,
        "federal_employer_identification_number": BANK3_FEIN,
        "master_account_rtn": BANK3_MRTN,
        "net_debit_cap": BANK3_NET_DEBIT_CAP,
        "sftp_username": BANK3,
        "server_certificate_expiry": None,
        "initial_balance": BANK3_INITIAL_BALANCE,
    },
    {
        "primary_routing_transit_number": BANK4_RTN,
        "legal_name": BANK4_LEGAL_NAME,
        "federal_employer_identification_number": BANK4_FEIN,
        "master_account_rtn": BANK4_MRTN,
        "net_debit_cap": BANK4_NET_DEBIT_CAP,
        "sftp_username": BANK4,
        "server_certificate_expiry": None,
        "initial_balance": BANK4_INITIAL_BALANCE,
    },
    {
        "primary_routing_transit_number": BANK5_RTN,
        "legal_name": BANK5_LEGAL_NAME,
        "federal_employer_identification_number": BANK5_FEIN,
        "master_account_rtn": BANK5_MRTN,
        "net_debit_cap": BANK5_NET_DEBIT_CAP,
        "sftp_username": BANK5,
        "server_certificate_expiry": None,
        "initial_balance": BANK5_INITIAL_BALANCE,
    },
]


if os.environ.get("AUTOMATED_CONFIG") == "true":
    automated_db_url = os.environ.get("DATABASE_URL")
    if not automated_db_url:
        logger.warning("AUTOMATED_CONFIG is enabled but DATABASE_URL is not set; skipping bank seeding")
    else:
        for bank_config in BANK_SEED_CONFIGS:
            seed_bank_to_database(automated_db_url, bank_config, FRB_ROUTING_NUMBER)
    

class AddAchBankRequest(BaseModel):
    primary_routing_transit_number: str
    legal_name: str
    federal_employer_identification_number: str
    master_account_rtn: str
    net_debit_cap: str
    sftp_username: str
    server_certificate_expiry: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "primary_routing_transit_number": "031000021",
                "legal_name": "Baguette Bank",
                "federal_employer_identification_number": "123456789",
                "master_account_rtn": "031000021",
                "net_debit_cap": "1000000",
                "sftp_username": "baguette-bank",
                "server_certificate_expiry": "2025-12-31"
            }
        }


class FundsTransferRequest(BaseModel):
    sender_master_account_rtn: str
    receiver_master_account_rtn: str
    amount_cents: float
    rail_type: str
    external_ref_id: Optional[str] = None
    effective_date: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "sender_master_account_rtn": FRB_ROUTING_NUMBER,
                "receiver_master_account_rtn": "031000021",
                "amount_cents": 1500050,
                "rail_type": "FedWire",
                "external_ref_id": "TXN-2026-001",
                "effective_date": "2026-05-16"
            }
        }

ach = FastAPI()

# Simplified CORS origins using ports passed via env (REACT_PORT, VITE_PORT)
ports = []
for key in ("REACT_PORT", "VITE_PORT"):
    v = os.environ.get(key)
    if v and v.strip():
        ports.append(v.strip().strip('"').strip("'"))
if not ports:
    ports = ["3000", "5173"]

hosts = ["localhost", "127.0.0.1"]
server_ip = os.environ.get("SERVER_IP")
if server_ip and server_ip.strip() and server_ip.strip() not in hosts:
    hosts.append(server_ip.strip())

allow_origins = [f"http://{h}:{p}" for h in hosts for p in ports]
logger.debug("CORS allow_origins: %s", allow_origins)

# Allow localhost/127.0.0.1 on any port by default (covers dev servers like port 3514).
# Can be overridden with ALLOW_ORIGIN_REGEX in the environment.
default_allow_origin_regex = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"
allow_origin_regex = os.environ.get("ALLOW_ORIGIN_REGEX", default_allow_origin_regex)
logger.debug("CORS allow_origin_regex: %s", allow_origin_regex)

ach.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@ach.get("/")
async def root():
    return {"message": "FastAPI ACH app running"}

@ach.get("/health", tags=["Control Panel - http://localhost:3310/"])
async def health():
    return {"status": "ok",
            "frb_routing_number": FRB_ROUTING_NUMBER,
            "frb_legal_name": FRB_LEGAL_NAME,
            "cors_allowed_origins": allow_origins} # TODO: Remove later

@ach.get("/env", tags = ["Testing"])
async def env():
    return {"DATABASE_URL": os.environ.get("DATABASE_URL")}

@ach.get("/api/sftp-users", tags=["Control Panel - http://localhost:3310/"])
async def sftp_users():
    list_of_users = []
    sftp_container = os.environ.get("SFTP_CONTAINER_NAME", "fedsystems-sftp")

    try:
        result = subprocess.run(
            ["docker", "exec", sftp_container, "cat", "/etc/passwd"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.splitlines():
            parts = line.split(":")
            if len(parts) < 7:
                continue
            username = parts[0]
            uid = parts[2]
            gid = parts[3]
            home = parts[5]
            shell = parts[6]

            # Keep non-system users so bank accounts are returned.
            if uid.isdigit() and int(uid) >= 1000 and username != "nobody":
                public_key = None
                public_key_path = f"/home/{username}/.ssh/keys/id_rsa.pub"
                try:
                    key_result = subprocess.run(
                        ["docker", "exec", sftp_container, "cat", public_key_path],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    public_key = key_result.stdout.strip() or None
                except Exception:
                    logger.debug("No public key found for %s at %s", username, public_key_path)

                list_of_users.append({
                    "username": username,
                    "uid": uid,
                    "gid": gid,
                    "home": home,
                    "shell": shell,
                    "public_key": public_key,
                })
    except Exception:
        logger.exception(
            "Failed to read passwd from sftp container %s, falling back to mounted volume",
            sftp_container,
        )

    return {"sftp_users": list_of_users}

@ach.get("/api/ach-banks", tags=["Control Panel - http://localhost:3310/"])
def ach_banks():
    """Return list of known banks with ACH participation status.

    Tries to query the configured Postgres `bank_details` and `ach_participants`
    tables. If the database is unreachable, falls back to reading declared
    BANK0..BANKn values from the parent `.env` file.
    """
    db_url = os.environ.get("DATABASE_URL")

    banks = []

    def make_entry_from_row(row):
        return {
            "primary_routing_transit_number": row.get("primary_routing_transit_number"),
            "legal_name": row.get("legal_name"),
            "master_account_rtn": row.get("master_account_rtn"),
            "sftp_username": row.get("sftp_username"),
            "ach_participant": bool(row.get("type")) if row is not None else False,
            "participant_type": row.get("type"),
            "restricted": bool(row.get("restricted")) if row.get("restricted") is not None else False,
        }

    if db_url:
        try:
            conn = psycopg2.connect(db_url, connect_timeout=5)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT bd.primary_routing_transit_number,
                       bd.legal_name,
                       bd.master_account_rtn,
                       bd.sftp_username,
                       ap.type,
                       ap.restricted
                FROM bank_details bd
                LEFT JOIN ach_participants ap
                  ON ap.primary_routing_transit_number = bd.primary_routing_transit_number
                ORDER BY bd.legal_name NULLS LAST
                """
            )
            rows = cur.fetchall()
            for r in rows:
                banks.append(make_entry_from_row(r))
            cur.close()
            conn.close()
            return {"banks": banks}
        except Exception:
            logger.exception("Failed to query DB for ACH banks, falling back to .env")

    return {"banks": banks}

@ach.post("/api/add-ach-bank", tags=["Control Panel - http://localhost:3310/"])
async def add_ach_bank(bank_data: AddAchBankRequest):
    """Add a new ACH bank to the system.

    Expects JSON body with keys (required):
      - primary_routing_transit_number
      - legal_name
      - master_account_rtn

    Optional keys: federal_employer_identification_number, net_debit_cap,
    sftp_username, server_certificate_expiry, ach_participant (bool),
    participant_type, restricted (bool).

    Inserts or updates `bank_details` and `ach_participants` when requested.
    """
    required = [
        "primary_routing_transit_number",
        "federal_employer_identification_number",
        "master_account_rtn",
        "net_debit_cap",
        "sftp_username",
    ]

    # Convert Pydantic model to dict for easier access
    bank_data_dict = bank_data.model_dump()

    for r in required:
        if r not in bank_data_dict or bank_data_dict.get(r) in (None, ""):
            raise HTTPException(status_code=400, detail=f"Missing required field: {r}")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured")

    prtn = bank_data_dict.get("primary_routing_transit_number")
    legal_name = bank_data_dict.get("legal_name")
    feid = bank_data_dict.get("federal_employer_identification_number")
    master_rtn = bank_data_dict.get("master_account_rtn")
    net_debit_cap = bank_data_dict.get("net_debit_cap")
    sftp_username = bank_data_dict.get("sftp_username")
    server_cert_expiry = bank_data_dict.get("server_certificate_expiry")

    # sftp_username must match an existing SFTP user
    sftp_username = bank_data_dict.get("sftp_username")
    try:
        sftp_resp = await sftp_users()
        valid_users = [u.get("username") for u in sftp_resp.get("sftp_users", [])]
    except Exception:
        valid_users = []

    if sftp_username not in valid_users:
        raise HTTPException(status_code=400, detail=f"sftp_username '{sftp_username}' not found in SFTP users")

    # ACH participant info: always set to 'both' and restricted 0 per request
    ach_participant = True
    participant_type = 'both'
    restricted = 0

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute(
            """
            INSERT INTO bank_details (primary_routing_transit_number, legal_name, federal_employer_identification_number, master_account_rtn, net_debit_cap, sftp_username, server_certificate_expiry)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (primary_routing_transit_number) DO UPDATE
              SET legal_name = EXCLUDED.legal_name,
                  federal_employer_identification_number = EXCLUDED.federal_employer_identification_number,
                  master_account_rtn = EXCLUDED.master_account_rtn,
                  net_debit_cap = EXCLUDED.net_debit_cap,
                  sftp_username = EXCLUDED.sftp_username,
                  server_certificate_expiry = EXCLUDED.server_certificate_expiry
            RETURNING *
            """,
            (prtn, legal_name, feid, master_rtn, net_debit_cap, sftp_username, server_cert_expiry),
        )

        created = cur.fetchone()

        # Always ach_participants row with type 'both' and restricted 0
        cur.execute(
            """
            INSERT INTO ach_participants (primary_routing_transit_number, type, restricted)
            VALUES (%s, %s, %s)
            ON CONFLICT (primary_routing_transit_number) DO UPDATE
              SET type = EXCLUDED.type,
                  restricted = EXCLUDED.restricted
            """,
            (prtn, participant_type, restricted),
        )

        conn.commit()
        cur.close()
        conn.close()

        return {"bank": created}
    except Exception as e:
        logger.exception("Failed to add/update ACH bank: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    
@ach.get("/api/current-balance", tags=["Control Panel - http://localhost:3310/"])
async def current_balance(master_account_rtn: str):
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
    
@ach.post("/api/funds-transfer", tags=["Control Panel - http://localhost:3310/"])
async def funds_transfer(transfer_data: FundsTransferRequest):
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

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured")

    sender_master_rtn = transfer_dict.get("sender_master_account_rtn")
    receiver_master_rtn = transfer_dict.get("receiver_master_account_rtn")
    amount_cents = transfer_dict.get("amount_cents")
    rail_type = transfer_dict.get("rail_type")
    external_ref_id = transfer_dict.get("external_ref_id")
    effective_date = transfer_dict.get("effective_date", datetime.utcnow().date().isoformat())

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

        cur.execute("LOCK TABLE central_ledger_entries IN EXCLUSIVE MODE")
        cur.execute("SELECT COALESCE(MAX(entry_id), 0) AS max_id FROM central_ledger_entries")
        max_id = cur.fetchone()["max_id"]

        if normalized_rail in two_leg_rails:
            if not sender_registered or not receiver_registered:
                raise HTTPException(
                    status_code=400,
                    detail="For ACH/FedNow, both sender and receiver must be registered banks",
                )

            credit_entry_id = max_id + 1
            debit_entry_id = max_id + 2

            cur.execute(
                """
                INSERT INTO central_ledger_entries (entry_id, master_account_rtn, activity_source_rtn, amount_cents, rail_type, external_ref_id, effective_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    credit_entry_id,
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
                INSERT INTO central_ledger_entries (entry_id, master_account_rtn, activity_source_rtn, amount_cents, rail_type, external_ref_id, effective_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    debit_entry_id,
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

            single_entry_id = max_id + 1
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
                INSERT INTO central_ledger_entries (entry_id, master_account_rtn, activity_source_rtn, amount_cents, rail_type, external_ref_id, effective_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    single_entry_id,
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

        return response_payload
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.exception("Failed to add funds transfer: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

class JsonToAchAddenda(BaseModel):
    addenda_type_code: Optional[str] = Field(None, description="Addenda type code, for example 05 for payment related information.")
    payment_related_information: str = Field(
        ..., description="Free-form addenda text, truncated to 80 characters if needed."
    )


class JsonToAchEntry(BaseModel):
    transaction_code: str = Field(..., description="ACH transaction code.")
    receiving_dfi_rtn: str = Field(..., description="9-digit receiving DFI routing number.")
    dfi_account_number: str = Field(..., description="Receiver account number.")
    amount_cents: int = Field(..., ge=0, description="Amount in cents.")
    individual_id_number: Optional[str] = Field(None, description="Optional individual ID number.")
    individual_name: Optional[str] = Field(None, description="Optional individual name.")
    trace_number: Optional[str] = Field(None, description="Optional trace number; generated if omitted.")
    addenda: Optional[list[JsonToAchAddenda]] = Field(None, description="Optional addenda records for the entry.")


class JsonToAchBatchHeader(BaseModel):
    company_name: str = Field(..., description="Originating company name.")
    company_identification: str = Field(..., description="Originator/company identification.")
    standard_entry_class_code: str = Field(..., description="SEC code, for example PPD or CCD.")
    originating_dfi_identification: str = Field(..., description="8-digit originating DFI identification.")
    service_class_code: Optional[str] = Field(None, description="Optional service class code; derived if omitted.")
    company_discretionary_data: Optional[str] = Field(None, description="Optional company discretionary data.")
    company_entry_description: Optional[str] = Field(None, description="Optional batch description.")
    company_descriptive_date: Optional[str] = Field(None, description="Optional descriptive date; defaults to file creation date.")
    effective_entry_date: Optional[str] = Field(None, description="Optional effective date; defaults to file creation date.")
    settlement_date: Optional[str] = Field(None, description="Optional settlement date placeholder.")
    originator_status_code: Optional[str] = Field(None, description="Optional originator status code; defaults to 1.")
    batch_number: Optional[str] = Field(None, description="Optional batch number; generated if omitted.")


class JsonToAchBatch(BaseModel):
    header: JsonToAchBatchHeader
    entries: list[JsonToAchEntry]


class JsonToAchFileHeader(BaseModel):
    immediate_destination: str = Field(..., description="Destination routing number.")
    immediate_origin: str = Field(..., description="Origin routing number.")
    immediate_destination_name: str = Field(..., description="Destination name.")
    immediate_origin_name: str = Field(..., description="Origin name.")
    file_creation_date: Optional[str] = Field(None, description="Optional YYMMDD file creation date; defaults to today.")
    file_creation_time: Optional[str] = Field(None, description="Optional HHMM file creation time; defaults to now.")
    file_id_modifier: Optional[str] = Field(None, description="Optional file ID modifier; defaults to A.")
    reference_code: Optional[str] = Field(None, description="Optional reference code.")


class JsonToAchFileData(BaseModel):
    header: JsonToAchFileHeader
    batches: list[JsonToAchBatch]


class JsonToAchRequest(BaseModel):
    data: JsonToAchFileData

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "data": {
                        "header": {
                            "immediate_destination": "090000515",
                            "immediate_origin": "040104018",
                            "immediate_destination_name": "FRB Tungsten",
                            "immediate_origin_name": "Baguette bank"
                        },
                        "batches": [
                            {
                                "header": {
                                    "company_name": "Baguette store",
                                    "company_identification": "1313131310",
                                    "standard_entry_class_code": "PPD",
                                    "originating_dfi_identification": "04010401"
                                },
                                "entries": [
                                    {
                                        "transaction_code": "22",
                                        "receiving_dfi_rtn": "010101012",
                                        "dfi_account_number": "123456789",
                                        "amount_cents": 100,
                                        "individual_name": "Leek store"
                                    }
                                ]
                            }
                        ]
                    }
                },
                {
                    "data": {
                        "header": {
                            "immediate_destination": "090000515",
                            "immediate_origin": "040104018",
                            "immediate_destination_name": "FRB Tungsten",
                            "immediate_origin_name": "Baguette store",
                            "file_creation_date": "260525",
                            "file_creation_time": "1200",
                            "file_id_modifier": "A",
                            "reference_code": ""
                        },
                        "batches": [
                            {
                                "header": {
                                    "service_class_code": "200",
                                    "company_name": "Baguette store",
                                    "company_discretionary_data": "",
                                    "company_identification": "1313131310",
                                    "standard_entry_class_code": "PPD",
                                    "company_entry_description": "LEEK PAY",
                                    "company_descriptive_date": "260525",
                                    "effective_entry_date": "260525",
                                    "settlement_date": "",
                                    "originator_status_code": "1",
                                    "originating_dfi_identification": "04010401",
                                    "batch_number": "0000001"
                                },
                                "entries": [
                                    {
                                        "transaction_code": "22",
                                        "receiving_dfi_rtn": "010101012",
                                        "dfi_account_number": "123456789",
                                        "amount_cents": 100,
                                        "individual_id_number": "",
                                        "individual_name": "Leek store",
                                        "trace_number": "040104010000001",
                                        "addenda": [
                                            {
                                                "payment_related_information": "31 tons of leek purchase!"
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        }


@ach.post("/json-to-ach", tags=["Helpers, banks can use this to generate/convert/validate ACH files"])
async def json_to_ach_helper(data: JsonToAchRequest, bank_rtn: Optional[str] = ""):
    """Convert JSON ACH file description to NACHA format string.

    # **This endpoint does not validate the file!**

    ## Too long values will be truncated.
     
    It will return it how you send it, even if it's wrong or incomplete.

    In the example you can see the minimal required data to produce a valid ACH file.

    ## Check out schemas `JsonToAchFileData` to see all the optional fields.

    Inside `FedSystems/ACH` you can find `sample_full_request.json` with fully filled out example data covering all fields.
    """
    try:
        ach_result = jsonToAchFile(data.data.model_dump(exclude_none=True))

        # Support either an ACHFile-like object, a list of NACHA lines, or plain text.
        if hasattr(ach_result, "build_ach") and callable(ach_result.build_ach):
            ach_lines = ach_result.build_ach()
            ach_content = "\n".join(ach_lines) if isinstance(ach_lines, list) else str(ach_lines)
        elif isinstance(ach_result, list):
            ach_content = "\n".join(str(line) for line in ach_result)
        else:
            ach_content = str(ach_result)

        filename = f"{bank_rtn}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.ach"
        return Response(
            content=ach_content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.exception("Failed to convert JSON to ACH: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    
def convertFileToLines(file_content: str):
    """Convert File content to list of lines, handling different newline formats."""
    return file_content.replace("\r\n", "\n").replace("\r", "\n").split("\n")

@ach.post("/ach-to-json", tags=["Helpers, banks can use this to generate/convert/validate ACH files"])
async def ach_to_json_helper(file: UploadFile):
    """Convert an uploaded ACH file to JSON format.

    # **This endpoint does not validate the file!**
    """
    try:
        achFile = ACHFile()
        content = await file.read()
        lines = convertFileToLines(content.decode("utf-8", errors="replace"))
        achFile.parse("", lines = lines)
        ach_json = achFileToJson(achFile)
        return ach_json
    except Exception as e:
        logger.exception("Failed to convert ACH to JSON: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

@ach.post("/validate-ach", tags=["Helpers, banks can use this to generate/convert/validate ACH files"])
async def validate_ach(file: UploadFile, immediate_destination_rtn: Optional[str] = None, immediate_origin_rtn: Optional[str] = None):
    """Validate an uploaded ACH file.

    - immediate_destination_rtn is optional, if provided it will check if the file's immediate destination matches it.
    - immediate_origin_rtn is optional, if provided it will check if the file's immediate origin matches it.

    Returns .ack file.
    """
    try:
        achFile = ACHFile()
        content = await file.read()
        lines = convertFileToLines(content.decode("utf-8", errors="replace"))
        filename = file.filename or None
        achFile.parse(file_path=filename, lines = lines, force_ack_on_format_error=True)
        validation_report = achFile.validate(is_parsed=True, immediate_destination=immediate_destination_rtn, immediate_origin=immediate_origin_rtn)
        ack_filename = f"{os.path.splitext(file.filename or 'validation')[0]}.ack"
        return Response(
            content=validation_report,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{ack_filename}"'},
        )
    except Exception as e:
        logger.exception("Failed to validate ACH file: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    
@ach.get("/collect", tags=["Session, Available in control panel -> session manager - http://localhost:3310/"])
def collect_inbound_files():
    """Collect files from each bank's inbound folder.

    # Runs automatically every 15 minutes, unless set to manual(default) mode.

    # If your .ach is being skipped, check if you're registered as an ACH participant and that your bank details include the correct `sftp_username` matching your SFTP user. You can check your registration status and details in the "ACH Banks" section of the control panel.

    # Available in control panel -> session manager - http://localhost:3310/ can be run from here too. Click the "Try it out" button and then "Execute" to run the collection process.

    # What to do as bank:

    - Create .ach file
    - Place it into your bank's inbound folder (for example `sftp_data/BANK0/inbound/`)
    - Run this endpoint to collect files.
    - You should find .ack file in your bank's outbound folder (for example `sftp_data/BANK0/outbound/`) with validation results. If successful, your .ach will be processed in next session.

    - Scans the mounted SFTP data directory (default `/app/sftp_data`).
    - Validates the file, sends .ack to the bank's outbound folder.
        - If validation fails, sends an .ack file with error details and deletes failed .ach file.
        - If validation succeeds, moves files from `<sftp_data>/<bank>/inbound/` to a directory as `collected/{bank_rtn}_<timestamp>.ach`, deletes the original file from the inbound folder and sends .ack file to the bank's outbound folder.
    """

    sftp_root = os.environ.get("SFTP_DATA_DIR", "/app/sftp_data")
    collected_root = os.environ.get("COLLECTED_DIR", "/app/collected")

    if not os.path.isdir(sftp_root):
        raise RuntimeError(f"SFTP data directory not found: {sftp_root}")

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_dir = collected_root
    os.makedirs(run_dir, exist_ok=True)

    db_url = os.environ.get("DATABASE_URL")

    def get_ach_participants():
        """Gets a list of participating DFIs RTNs from the database."""
        if not db_url:
            return []

        conn = None
        cur = None
        try:
            conn = psycopg2.connect(db_url, connect_timeout=5)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT primary_routing_transit_number
                FROM ach_participants
                WHERE restricted not in (1, 'restricted') 
                """
            )
            rows = cur.fetchall()
            return [row.get("primary_routing_transit_number") for row in rows]
        except Exception:
            logger.exception("Failed to get ACH participants")
            return []
        finally:
            if cur is not None:
                cur.close()
            if conn is not None:
                conn.close()

    def lookup_bank_rtn(sftp_username):
        if not db_url:
            return None

        conn = None
        cur = None
        try:
            conn = psycopg2.connect(db_url, connect_timeout=5)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT primary_routing_transit_number
                FROM bank_details
                WHERE sftp_username = %s
                """,
                (sftp_username,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return row.get("primary_routing_transit_number")
        except Exception:
            logger.exception("Failed to look up bank RTN for sftp user %s", sftp_username)
            return None
        finally:
            if cur is not None:
                cur.close()
            if conn is not None:
                conn.close()

    def check_if_restricted(rtn):
        if not db_url:
            return False

        conn = None
        cur = None
        try:
            conn = psycopg2.connect(db_url, connect_timeout=5)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT restricted
                FROM ach_participants
                WHERE primary_routing_transit_number = %s
                """,
                (rtn,),
            )
            row = cur.fetchone()
            if not row:
                return False
            return row.get("restricted", False)
        except Exception:
            logger.exception("Failed to check if bank RTN %s is restricted", rtn)
            return False

    def validate_ach_bytes(file_bytes, filename=None, immediate_origin_rtn=None):
        ach_file = ACHFile()
        lines = convertFileToLines(file_bytes.decode("utf-8", errors="replace"))
        ach_file.parse(file_path=filename, lines=lines, force_ack_on_format_error=True)
        ack_text = ach_file.validate(is_parsed=True, immediate_origin=immediate_origin_rtn, participating_dfi_rtns=get_ach_participants())
        ack_lines = ack_text.splitlines()
        is_valid = len(ack_lines) > 1 and ack_lines[1].startswith("R,")
        return ack_text, is_valid

    def write_ack_file(outbound_dir, source_filename, ack_text):
        os.makedirs(outbound_dir, exist_ok=True)
        ack_basename = os.path.splitext(source_filename or "validation")[0] + ".ack"
        ack_path = os.path.join(outbound_dir, ack_basename)
        with open(ack_path, "w", encoding="utf-8", newline="\n") as ack_file:
            ack_file.write(ack_text)
        return ack_path

    report = {
        "run": timestamp,
        "collected_at": datetime.utcnow().isoformat() + "Z",
        "info": "Make sure your bank is registred as an ACH participant. Unregistered banks will be skipped.",
        "entries": []
    }

    # Iterate bank folders in sftp root
    for bank in sorted(os.listdir(sftp_root)):
        bank_dir = os.path.join(sftp_root, bank)
        if not os.path.isdir(bank_dir):
            continue

        bank_rtn = lookup_bank_rtn(bank)
        if not bank_rtn:
            logger.warning("Skipping bank folder %s because no bank RTN was found for sftp_username=%s", bank_dir, bank)
            continue

        inbound_dir = os.path.join(bank_dir, "inbound")
        if not os.path.isdir(inbound_dir):
            continue

        outbound_dir = os.path.join(bank_dir, "outbound")
        os.makedirs(outbound_dir, exist_ok=True)

        for entry in sorted(os.listdir(inbound_dir)):
            src_path = os.path.join(inbound_dir, entry)
            if not os.path.isfile(src_path):
                continue

            is_restricted = check_if_restricted(bank_rtn)
            if is_restricted == "restricted":
                ack_file = write_ack_file(os.path.join(bank_dir, "outbound"), entry, f"Bank with RTN {bank_rtn} is currently restricted and cannot send ACH files. Please contact support for more information.")
                report["entries"].append({
                    "bank_rtn": bank_rtn,
                    "sftp_username": bank,
                    "status": "restricted",
                    "ack_path": ack_file,
                })
                os.remove(src_path)
                continue

            try:
                with open(src_path, "rb") as f:
                    file_bytes = f.read()

                ack_text, is_valid = validate_ach_bytes(file_bytes, filename=entry, immediate_origin_rtn=bank_rtn)
                ack_path = write_ack_file(outbound_dir, entry, ack_text)

                if is_valid:
                    target_filename = f"{bank_rtn}_{os.path.basename(entry)}"
                    target_path = os.path.join(run_dir, target_filename)
                    # Overwrite existing collected file if present.
                    if os.path.exists(target_path):
                        try:
                            os.remove(target_path)
                        except Exception:
                            logger.exception("Failed to remove existing target file %s", target_path)
                    shutil.move(src_path, target_path)
                    report["entries"].append({
                        "bank": bank_rtn,
                        "sftp_username": bank,
                        "filename": entry,
                        "status": "collected",
                        "size": os.path.getsize(target_path),
                        "collected_path": target_path,
                        "ack_path": ack_path,
                    })
                else:
                    os.remove(src_path)
                    report["entries"].append({
                        "bank_rtn": bank_rtn,
                        "sftp_username": bank,
                        "filename": entry,
                        "status": "rejected",
                        "ack_path": ack_path,
                    })
            except Exception as e:
                logging.exception("Failed processing %s", src_path)
                report["entries"].append({
                    "bank_rtn": bank_rtn,
                    "sftp_username": bank,
                    "filename": entry,
                    "status": "error",
                    "error": str(e)
                })

    return report
