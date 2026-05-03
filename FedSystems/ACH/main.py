from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import subprocess
import logging
import shutil
import json
import base64
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

ach = FastAPI()

@ach.get("/")
async def root():
    return {"message": "FastAPI ACH app running"}

@ach.get("/health")
async def health():
    return {"status": "ok"}

@ach.get("/env")
async def env():
    return {"DATABASE_URL": os.environ.get("DATABASE_URL")}

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

    
