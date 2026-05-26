from fastapi import APIRouter, HTTPException, Body, Depends, Header
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import secrets
from database import get_db, Bank, Transaction, NettingReport, GridlockQueue
from schemas import LiquidityInjection, BankCreate
from services.xml_service import validate_xml_schema, extract_rtp_data
from services.gridlock_service import resolve_gridlock

router = APIRouter()

# kody błędów ISO 20022
ISO_ERROR_CODES = {
    "AM04": "Insufficient funds",
    "AM03": "Blocked account",
    "AC03": "Invalid creditor account",
    "DU01": "Duplicate payment"
}

TIME_TO_RECOVER_SECONDS = 60

# ZABEZPIECZENIE TOŻSAMOŚCI
def get_current_bank(x_api_key: str = Header(...), db: Session = Depends(get_db)):
    """Sprawdza, czy bank posiada ważny klucz API w nagłówku zapytania"""
    bank = db.query(Bank).filter(Bank.api_key == x_api_key).first()
    if not bank:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key.")
    return bank

def check_timeouts(db: Session):
    now = datetime.now(timezone.utc)
    banks = db.query(Bank).filter(Bank.status == "ACTIVE", Bank.limit_exceeded_at.is_not(None)).all()
    for bank in banks:
        time_passed = (now - bank.limit_exceeded_at).total_seconds()
        if time_passed > TIME_TO_RECOVER_SECONDS:
            bank.status = "BLOCKED"
    db.commit()


# ENDPOINTY ZARZĄDZANIA BANKAMI
@router.post("/banks", tags=["Bank"])
def register_bank(bank_data: BankCreate, db: Session = Depends(get_db)):
    existing_bank = db.query(Bank).filter(Bank.bank_code == bank_data.bank_code).first()
    if existing_bank:
        raise HTTPException(status_code=400, detail=f"Bank with code {bank_data.bank_code} already exists.")
    
    new_api_key = f"key-{secrets.token_hex(8)}"
    
    new_bank = Bank(
        bank_code=bank_data.bank_code,
        balance=bank_data.balance,
        debt_limit=bank_data.debt_limit,
        status="ACTIVE",
        api_key=new_api_key
    )
    
    db.add(new_bank)
    db.commit()
    
    return {
        "message": f"Bank {bank_data.bank_code} registered successfully.",
        "api_key": new_api_key,
        "instructions": "use the API key for transfer requests"
    }

@router.post("/banks/{bank_code}/reset-key", tags=["Bank"])
def reset_bank_api_key(bank_code: str, db: Session = Depends(get_db)):
    bank = db.query(Bank).filter(Bank.bank_code == bank_code).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found.")
    
    new_api_key = f"key-{secrets.token_hex(8)}"
    bank.api_key = new_api_key
    db.commit()
    
    return {
        "message": f"API Key reset for {bank_code}.",
        "new_api_key": new_api_key
    }

@router.patch("/banks/{bank_code}/status", tags=["Bank"])
def update_bank_status(bank_code: str, status_update: dict, db: Session = Depends(get_db)):
    bank = db.query(Bank).filter(Bank.bank_code == bank_code).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found.")
    bank.status = status_update['status']
    db.commit()
    return {"message": f"Status for {bank_code} updated to {bank.status}"}

@router.get("/banks", tags=["RTP GUI"])
def get_banks_status(db: Session = Depends(get_db)):
    check_timeouts(db)
    banks = db.query(Bank).all()
    return {
        b.bank_code: {
            "balance": b.balance, 
            "debt_limit": b.debt_limit, 
            "status": b.status, 
            "limit_exceeded_at": b.limit_exceeded_at.isoformat() + ("Z" if not b.limit_exceeded_at.tzinfo else "") if b.limit_exceeded_at else None
        } for b in banks
    }

# ENDPOINTY TRANSAKCYJNE I GUI
@router.get("/transactions", tags=["RTP GUI"])
def get_transactions(db: Session = Depends(get_db)):
    txs = db.query(Transaction).order_by(Transaction.id.desc()).limit(50).all()
    return [
        {
            "id": t.id, 
            "sender": t.sender_code, 
            "receiver": t.receiver_code, 
            "amount": t.amount, 
            "status": t.status,
            "message_id": t.message_id, 
            "timestamp": t.timestamp.isoformat() + ("Z" if not t.timestamp.tzinfo else "") if t.timestamp else None,
            "debtor_name": getattr(t, "debtor_name", None),
            "creditor_name": getattr(t, "creditor_name", None)
        } for t in txs
    ]

@router.get("/netting-reports", tags=["RTP GUI"])
def get_netting_reports(db: Session = Depends(get_db)):
    reports = db.query(NettingReport).order_by(NettingReport.id.desc()).limit(20).all()
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "bank_code": r.bank_code,
            "net_position": r.net_position,
            "status": r.status,
            "timestamp": r.timestamp.isoformat() + ("Z" if not r.timestamp.tzinfo else "") if r.timestamp else None
        } for r in reports
    ]

@router.get("/queue", tags=["RTP GUI"])
def get_gridlock_queue(db: Session = Depends(get_db)):
    queue_items = db.query(GridlockQueue).all()
    parsed_queue = []
    for item in queue_items:
        try:
            data = extract_rtp_data(item.xml_payload)
            parsed_queue.append({
                "id": item.id,
                "amount": data["amount"],
                "sender": data["sender_code"],
                "receiver": data["receiver_code"]
            })
        except Exception:
            pass
    return parsed_queue

@router.post("/transfer", tags=["Core System"])
async def process_transfer(
    xml_data: str = Body(..., media_type="application/xml"), 
    db: Session = Depends(get_db),
    current_bank: Bank = Depends(get_current_bank)
):
    check_timeouts(db)
    
    try:
        # walidacja schematu
        validate_xml_schema(xml_data)
        
        # Ekstrakcja danych
        data = extract_rtp_data(xml_data)
        amount = data["amount"]
        currency = data["currency"]
        sender_code = data["sender_code"]
        receiver_code = data["receiver_code"]
        e2e_id = data["end_to_end_id"]
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ISO 20022 XML format.")

    if currency not in ["USD"]:
        raise HTTPException(status_code=400, detail=f"Currency {currency} not supported.")

    if current_bank.bank_code != sender_code:
        raise HTTPException(status_code=403, detail="Unauthorized sender.")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Transfer amount must be positive.")

    # Ochrona przed podwójnym przelewem (DU01)
    existing_tx = db.query(Transaction).filter(Transaction.message_id == e2e_id).first()
    if existing_tx:
        return {"status": "DUPLICATE", "code": "DU01", "message": ISO_ERROR_CODES["DU01"]}

    # Walidacja odbiorcy (AC03)
    receiver = db.query(Bank).filter(Bank.bank_code == receiver_code).first()
    if not receiver:
        raise HTTPException(status_code=404, detail={"code": "AC03", "message": ISO_ERROR_CODES["AC03"]})

    # Blokada banku (AM03)
    if current_bank.status == "BLOCKED":
        return {"status": "REJECTED", "code": "AM03", "message": ISO_ERROR_CODES["AM03"]}

    # Walidacja środków
    available_funds = current_bank.balance + current_bank.debt_limit
    if amount <= available_funds:
        current_bank.balance -= amount
        receiver.balance += amount
        if current_bank.balance >= -current_bank.debt_limit:
            current_bank.limit_exceeded_at = None
            
        new_tx = Transaction(
            sender_code=current_bank.bank_code, 
            receiver_code=receiver.bank_code, 
            amount=amount, 
            status="STANDARD", 
            message_id=e2e_id,
            debtor_name=data.get("debtor_name"),
            debtor_account=data.get("debtor_account"),
            creditor_name=data.get("creditor_name"),
            creditor_account=data.get("creditor_account")
        )
        db.add(new_tx)
        db.commit()
        return {"status": "ACCEPTED", "message": "Settlement completed."}
    else:
        # Brak środków - Dodajemy do kolejki
        db.add(GridlockQueue(xml_payload=xml_data))
        if current_bank.limit_exceeded_at is None:
            current_bank.limit_exceeded_at = datetime.now(timezone.utc)
        db.commit()
        
        # Próba automatycznego rozliczenia
        resolve_gridlock(db)
        
        queue_size = db.query(GridlockQueue).count()
        return {
            "status": "GRIDLOCK_QUEUED", 
            "code": "AM04", 
            "message": ISO_ERROR_CODES["AM04"], 
            "queue_size": queue_size
        }

@router.post("/central-bank/inject", tags=["Bank"])
def inject_liquidity(injection: LiquidityInjection, db: Session = Depends(get_db)):
    bank = db.query(Bank).filter(Bank.bank_code == injection.bank_code).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Institution not found.")
        
    bank.balance += injection.amount
    if bank.balance >= -bank.debt_limit:
        bank.status = "ACTIVE"
        bank.limit_exceeded_at = None
        
    new_tx = Transaction(sender_code="CENTRAL_BANK", receiver_code=bank.bank_code, amount=injection.amount, status="INJECTION")
    db.add(new_tx)
    
    db.commit()
    return {"status": "RESTORED", "message": f"Liquidity restored for {bank.bank_code}."}