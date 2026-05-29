from fastapi import APIRouter, HTTPException, Body, Depends, Header, Response, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from pydantic import BaseModel
import secrets
from database import get_db, Bank, Transaction, NettingReport, GridlockQueue, MessageQueue
from schemas import LiquidityInjection, BankCreate, SettlementRequest
from services.xml_service import validate_xml_schema, extract_pacs002_data, extract_rtp_data, generate_pacs002, validate_pacs002_schema
from services.gridlock_service import resolve_gridlock

router = APIRouter()

# Kody błędów ISO 20022
ISO_ERROR_CODES = {
    "AM04": "Insufficient funds",
    "AM03": "Blocked account",
    "AC03": "Invalid creditor account",
    "DU01": "Duplicate payment"
}

TIME_TO_RECOVER_SECONDS = 60

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

@router.post("/transfers", tags=["Core System"])
async def process_transfer(
    xml_data: str = Body(..., media_type="application/xml"), 
    db: Session = Depends(get_db),
    current_bank: Bank = Depends(get_current_bank)
):
    """Odbiera pacs.008, weryfikuje salda, odrzuca lub kolejkuje do odbioru (MQ) i zwraca pacs.002."""
    check_timeouts(db)
    
    data = {} 
    
    try:
        # walidacja schematu
        validate_xml_schema(xml_data)
        
        # Ekstrakcja danych
        data = extract_rtp_data(xml_data)
        
        data["sender_name"] = current_bank.bank_code
        data["receiver_name"] = data["receiver_code"]
        amount = data["amount"]
        currency = data["currency"]
        sender_code = data["sender_code"]
        receiver_code = data["receiver_code"]
        e2e_id = data["end_to_end_id"]
        
    except ValueError as ve:
        return Response(content=generate_pacs002(data, "RJCT"), media_type="application/xml", status_code=400)
    except Exception:
        return Response(content=generate_pacs002(data, "RJCT"), media_type="application/xml", status_code=400)

    if currency not in ["USD"]:
        return Response(content=generate_pacs002(data, "RJCT"), media_type="application/xml", status_code=400)

    if current_bank.bank_code != sender_code:
        return Response(content=generate_pacs002(data, "RJCT"), media_type="application/xml", status_code=403)

    if amount <= 0:
        return Response(content=generate_pacs002(data, "RJCT"), media_type="application/xml", status_code=400)

    # Ochrona przed podwójnym przelewem (DU01)
    existing_tx = db.query(Transaction).filter(Transaction.message_id == e2e_id).first()
    if existing_tx:
        return Response(content=generate_pacs002(data, "RJCT"), media_type="application/xml", status_code=409)

    # Walidacja odbiorcy (AC03)
    receiver = db.query(Bank).filter(Bank.bank_code == receiver_code).first()
    if not receiver:
        return Response(content=generate_pacs002(data, "RJCT"), media_type="application/xml", status_code=404)

    # Blokada banku (AM03)
    if current_bank.status == "BLOCKED":
        return Response(content=generate_pacs002(data, "RJCT"), media_type="application/xml", status_code=403)

    # Walidacja środków
    available_funds = current_bank.balance + current_bank.debt_limit
    
    if amount <= available_funds:
        # kolejkowanie dla odbiorcy gdy są środki
        
        # Odbiorca musi zaakceptować u siebie przelew
        if current_bank.balance >= -current_bank.debt_limit:
            current_bank.limit_exceeded_at = None
            
        new_tx = Transaction(
            sender_code=current_bank.bank_code, 
            receiver_code=receiver.bank_code, 
            amount=amount, 
            status="PENDING",
            message_id=e2e_id,
            debtor_name=data.get("debtor_name"),
            debtor_account=data.get("debtor_account"),
            creditor_name=data.get("creditor_name"),
            creditor_account=data.get("creditor_account")
        )
        db.add(new_tx)

        # Wrzucenie do kolejki dla banku odbiorcy
        new_message = MessageQueue(
            owner_bank_code=receiver.bank_code,
            message_type="pacs.008",
            message_id=e2e_id,
            payload=xml_data,
            status="PENDING"
        )
        db.add(new_message)
        db.commit()
        
        # ACTC - Accepted Technical Validation
        return Response(content=generate_pacs002(data, "ACTC"), media_type="application/xml", status_code=202)
        
    else:
        # gridlock dla braku środków (AM04)
        
        # Dodajemy do kolejki Gridlock
        db.add(GridlockQueue(xml_payload=xml_data))
        if current_bank.limit_exceeded_at is None:
            current_bank.limit_exceeded_at = datetime.now(timezone.utc)
        db.commit()
        
        # automatyczne rozliczanie przelewów
        resolve_gridlock(db)
        
        # zwracamy PDNG (Pending) potwierdzenie o przyjeciu przelewu, ale jest w kolejce gridlocka
        return Response(content=generate_pacs002(data, "PDNG"), media_type="application/xml", status_code=202)

@router.get("/queue/incoming", tags=["MQ Core System"])
async def get_incoming_messages(
    limit: int = Query(10, description="Maksymalna liczba wiadomosci do pobrania"),
    db: Session = Depends(get_db),
    current_bank: Bank = Depends(get_current_bank)
):
    """Endpoint dla banków do pobierania nowych, oczekujących przelewów z ich kolejki."""
    messages = db.query(MessageQueue).filter(
        MessageQueue.owner_bank_code == current_bank.bank_code,
        MessageQueue.status == "PENDING"
    ).limit(limit).all()

    response_data = []
    for msg in messages:
        response_data.append({
            "queue_id": msg.id,
            "message_id": msg.message_id,
            "type": msg.message_type,
            "payload": msg.payload 
        })
        msg.status = "FETCHED"

    db.commit()
    return {"messages": response_data}

@router.post("/transfers/settle", tags=["MQ Core System"])
async def settle_transfer(
    xml_data: str = Body(..., media_type="application/xml"),
    db: Session = Depends(get_db),
    current_bank: Bank = Depends(get_current_bank)
):
    """Endpoint dla banku docelowego. Odsyła plik pacs.002, co uwalnia środki i powiadamia nadawcę."""

    try:
        validate_pacs002_schema(xml_data)
        
        pacs002_data = extract_pacs002_data(xml_data)
        e2e_id = pacs002_data["end_to_end_id"]
        status = pacs002_data["status"]
    except Exception as e:
        print(f"BŁĄD WALIDACJI LUB PARSOWANIA XML: {e}")
        return Response(content=generate_pacs002({"end_to_end_id": "UNKNOWN"}, "RJCT"), media_type="application/xml", status_code=400)

    transaction = db.query(Transaction).filter(Transaction.message_id == e2e_id).first()
    
    if not transaction:
        return Response(content=generate_pacs002({"end_to_end_id": e2e_id}, "RJCT"), media_type="application/xml", status_code=404)
        
    if transaction.status != "PENDING":
        return Response(content=generate_pacs002({"end_to_end_id": e2e_id}, "RJCT"), media_type="application/xml", status_code=400)

    if transaction.receiver_code != current_bank.bank_code:
        return Response(content=generate_pacs002({"end_to_end_id": e2e_id}, "RJCT"), media_type="application/xml", status_code=403)

    sender = db.query(Bank).filter(Bank.bank_code == transaction.sender_code).first()

    if status == "ACCP":
        sender.balance -= transaction.amount
        current_bank.balance += transaction.amount
        transaction.status = "COMPLETED"
    else:
        transaction.status = "REJECTED"

    msg_in_queue = db.query(MessageQueue).filter(
        MessageQueue.message_id == e2e_id, 
        MessageQueue.owner_bank_code == current_bank.bank_code
    ).first()
    if msg_in_queue:
        msg_in_queue.status = "PROCESSED"

    response_data = {
        "end_to_end_id": transaction.message_id,
        "msg_id": transaction.message_id,
        "sender_name": transaction.sender_code,
        "receiver_name": current_bank.bank_code,
        "amount": transaction.amount,
        "currency": "USD",
        "debtor_name": transaction.debtor_name or "UNKNOWN",
        "debtor_account": transaction.debtor_account or "UNKNOWN",
        "creditor_name": transaction.creditor_name or "UNKNOWN",
        "creditor_account": transaction.creditor_account or "UNKNOWN"
    }

    return_message = MessageQueue(
        owner_bank_code=transaction.sender_code,
        message_type="pacs.002",
        message_id=e2e_id,
        payload=xml_data,
        status="PENDING"
    )
    db.add(return_message)

    db.commit()

    # Zwracamy Bankowi potwierdzenie o odebraniu pacs.002
    return Response(content=generate_pacs002(response_data, "ACTC"), media_type="application/xml", status_code=200)

@router.post("/central-bank/inject", tags=["Bank"])
def inject_liquidity(injection: LiquidityInjection, db: Session = Depends(get_db)):
    """Zastrzyk płynności dla zablokowanego banku."""
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