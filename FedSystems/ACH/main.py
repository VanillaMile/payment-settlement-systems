from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import re
import subprocess
import logging
import shutil
import json
import base64
from datetime import datetime
import psycopg2
import psycopg2.extras

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ach = FastAPI()

ach.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@ach.get("/")
async def root():
    return {"message": "FastAPI ACH app running"}

@ach.get("/health")
async def health():
    return {"status": "ok"}

@ach.get("/env")
async def env():
    return {"DATABASE_URL": os.environ.get("DATABASE_URL")}

@ach.get("/api/sftp-users")
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

@ach.get("/api/ach-banks")
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

@ach.post("/api/add-ach-bank")
async def add_ach_bank(bank_data: dict):
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

    for r in required:
        if r not in bank_data or bank_data.get(r) in (None, ""):
            raise HTTPException(status_code=400, detail=f"Missing required field: {r}")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured")

    prtn = bank_data.get("primary_routing_transit_number")
    legal_name = bank_data.get("legal_name")
    feid = bank_data.get("federal_employer_identification_number")
    master_rtn = bank_data.get("master_account_rtn")
    net_debit_cap = bank_data.get("net_debit_cap")
    sftp_username = bank_data.get("sftp_username")
    server_cert_expiry = bank_data.get("server_certificate_expiry")

    # sftp_username must match an existing SFTP user
    sftp_username = bank_data.get("sftp_username")
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
    
@ach.get("/api/current-balance")
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
    
@ach.post("/api/add-funds-transfer")
async def add_funds_transfer(transfer_data: dict):
    """Create transfer ledger entries and update running balances.

    Required JSON keys:
      - sender_master_account_rtn
      - receiver_master_account_rtn
      - amount
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
        "amount",
        "rail_type",
    ]
    for r in required:
        if r not in transfer_data or transfer_data.get(r) in (None, ""):
            raise HTTPException(status_code=400, detail=f"Missing required field: {r}")

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="Database not configured")

    sender_master_rtn = transfer_data.get("sender_master_account_rtn")
    receiver_master_rtn = transfer_data.get("receiver_master_account_rtn")
    amount = transfer_data.get("amount")
    rail_type = transfer_data.get("rail_type")
    external_ref_id = transfer_data.get("external_ref_id")
    effective_date = transfer_data.get("effective_date", datetime.utcnow().date().isoformat())

    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount must be numeric")

    if amount_value <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")

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

def collect_inbound_files():
    # TODO: PLACEHOLDER - Change this function to actually collect files from the SFTP inbound folders, move them to a collection directory, and produce a report. This is just a stub for now.
    """Collect files from each bank's inbound folder.

    - Scans the mounted SFTP data directory (default `/app/sftp_data`).
    - Moves files from `<sftp_data>/<bank>/inbound/` to a timestamped
      collection directory `/app/collected/<timestamp>/<bank>/`.
    - Produces a JSON report `/app/collected/<timestamp>/report.json` with
      entries: bank, filename, size, and file content (text when possible,
      otherwise base64).

    Returns the report as a Python dict.
    """

    sftp_root = os.environ.get("SFTP_DATA_DIR", "/app/sftp_data")
    collected_root = os.environ.get("COLLECTED_DIR", "/app/collected")

    if not os.path.isdir(sftp_root):
        raise RuntimeError(f"SFTP data directory not found: {sftp_root}")

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_dir = os.path.join(collected_root, timestamp)
    os.makedirs(run_dir, exist_ok=True)

    report = {
        "run": timestamp,
        "collected_at": datetime.utcnow().isoformat() + "Z",
        "entries": []
    }

    # Iterate bank folders in sftp root
    for bank in sorted(os.listdir(sftp_root)):
        bank_dir = os.path.join(sftp_root, bank)
        if not os.path.isdir(bank_dir):
            continue

        inbound_dir = os.path.join(bank_dir, "inbound")
        if not os.path.isdir(inbound_dir):
            continue

        target_bank_dir = os.path.join(run_dir, bank)
        os.makedirs(target_bank_dir, exist_ok=True)

        for entry in sorted(os.listdir(inbound_dir)):
            src_path = os.path.join(inbound_dir, entry)
            if not os.path.isfile(src_path):
                continue

            target_path = os.path.join(target_bank_dir, entry)
            # Move the file into collected folder
            shutil.move(src_path, target_path)

            # Read file content safely
            try:
                with open(target_path, "rb") as f:
                    data = f.read()
                # Try decode as UTF-8 text
                try:
                    text = data.decode("utf-8")
                    content = {"type": "text", "value": text}
                except Exception:
                    b64 = base64.b64encode(data).decode("ascii")
                    content = {"type": "base64", "value": b64}
                size = os.path.getsize(target_path)

                report["entries"].append({
                    "bank": bank,
                    "filename": entry,
                    "size": size,
                    "content": content
                })
            except Exception as e:
                logging.exception("Failed processing %s", target_path)
                report["entries"].append({
                    "bank": bank,
                    "filename": entry,
                    "error": str(e)
                })

    # Write report to disk
    report_path = os.path.join(run_dir, "report.json")
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(report, rf, indent=2, ensure_ascii=False)

    # For testing: write a copy of the report into each bank's outbound folder
    for bank in sorted(os.listdir(sftp_root)):
        bank_dir = os.path.join(sftp_root, bank)
        if not os.path.isdir(bank_dir):
            continue
        outbound_dir = os.path.join(bank_dir, "outbound")
        try:
            os.makedirs(outbound_dir, exist_ok=True)
            out_report_path = os.path.join(outbound_dir, f"report_{timestamp}.json")
            with open(out_report_path, "w", encoding="utf-8") as of:
                json.dump(report, of, indent=2, ensure_ascii=False)
            logger.debug("Wrote report to %s", out_report_path)
        except Exception:
            logger.exception("Failed writing report to outbound for %s", bank)

    return report


@ach.post("/collect")
async def collect_endpoint():
    try:
        report = collect_inbound_files()
        return report
    except Exception as e:
        logger.exception("Collect failed")
        raise HTTPException(status_code=500, detail=str(e))

    
