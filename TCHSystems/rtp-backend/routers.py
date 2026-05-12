from fastapi import APIRouter, HTTPException, Body, Depends
from sqlalchemy.orm import Session
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timezone
from database import get_db, Bank, Transaction, NettingReport
from schemas import LiquidityInjection

router = APIRouter()

TIME_TO_RECOVER_SECONDS = 60
gridlock_queue = []

def check_timeouts(db: Session):
    # używamy czasu UTC, zgodnego z bazą danych
    now = datetime.now(timezone.utc)
    banks = db.query(Bank).filter(Bank.status == "ACTIVE", Bank.limit_exceeded_at.is_not(None)).all()
    for bank in banks:
        time_passed = (now - bank.limit_exceeded_at).total_seconds()
        if time_passed > TIME_TO_RECOVER_SECONDS:
            bank.status = "BLOCKED"
    db.commit()

@router.get("/banks", tags=["RTP GUI"])
def get_banks_status(db: Session = Depends(get_db)):
    check_timeouts(db)
    banks = db.query(Bank).all()
    return {
        b.bank_code: {
            "balance": b.balance, 
            "debt_limit": b.debt_limit, 
            "status": b.status, 
            # Wysyłamy datę w formacie ISO z oznaczeniem UTC, aby frontend mógł poprawnie ją zinterpretować
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
            "timestamp": t.timestamp.isoformat() + ("Z" if not t.timestamp.tzinfo else "") if t.timestamp else None
        } for t in txs
    ]

@router.get("/netting-reports", tags=["RTP GUI"])
def get_netting_reports(db: Session = Depends(get_db)):
    """Pobieranie raportów z sesji (Komunikacja zwrotna dla banków)"""
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
def get_gridlock_queue():
    parsed_queue = []
    for xml_string in gridlock_queue:
        root = ET.fromstring(xml_string)
        parsed_queue.append({
            "amount": float(root.find('.//IntrBkSttlmAmt').text),
            "sender": root.find('.//DbtrAgt/FinInstnId/BICFI').text,
            "receiver": root.find('.//CdtrAgt/FinInstnId/BICFI').text
        })
    return parsed_queue

@router.patch("/banks/{bank_code}/status")
def update_bank_status(bank_code: str, status_update: dict, db: Session = Depends(get_db)):
    bank = db.query(Bank).filter(Bank.bank_code == bank_code).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Bank not found.")
    bank.status = status_update['status']
    db.commit()
    return {"message": f"Status for {bank_code} updated to {bank.status}"}

@router.post("/transfer", tags=["Core System"])
async def process_transfer(xml_data: str = Body(..., media_type="application/xml"), db: Session = Depends(get_db)):
    check_timeouts(db)
    try:
        xml_string = re.sub(' xmlns="[^"]+"', '', xml_data)
        root = ET.fromstring(xml_string)
        amount = float(root.find('.//IntrBkSttlmAmt').text)
        sender_code = root.find('.//DbtrAgt/FinInstnId/BICFI').text
        receiver_code = root.find('.//CdtrAgt/FinInstnId/BICFI').text
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid XML format.")

    sender = db.query(Bank).filter(Bank.bank_code == sender_code).first()
    receiver = db.query(Bank).filter(Bank.bank_code == receiver_code).first()

    if not sender or not receiver:
        raise HTTPException(status_code=404, detail="Bank not found.")
    if sender.status == "BLOCKED":
        return {"status": "REJECTED", "message": f"Institution {sender.bank_code} is blocked."}

    available_funds = sender.balance + sender.debt_limit

    if amount <= available_funds:
        sender.balance -= amount
        receiver.balance += amount
        if sender.balance >= -sender.debt_limit:
            sender.limit_exceeded_at = None
            
        new_tx = Transaction(sender_code=sender.bank_code, receiver_code=receiver.bank_code, amount=amount, status="STANDARD")
        db.add(new_tx)
        db.commit()
        return {"status": "ACCEPTED", "message": "Settlement completed."}
    else:
        gridlock_queue.append(xml_string)
        if sender.limit_exceeded_at is None:
            # Zapisujemy początek blokady używając UTC
            sender.limit_exceeded_at = datetime.now(timezone.utc)
            db.commit()
        
        resolve_gridlock(db)
        
        return {
            "status": "GRIDLOCK_QUEUED", 
            "message": "Insufficient liquidity. Order queued.", 
            "queue_size": len(gridlock_queue)
        }

@router.post("/gridlock-resolve", tags=["Core System"])
def resolve_gridlock(db: Session = Depends(get_db)):
    if not gridlock_queue:
        return {"status": "EMPTY_QUEUE", "message": "No pending orders."}

    net_positions = {}
    for xml_string in gridlock_queue:
        root = ET.fromstring(xml_string)
        amount = float(root.find('.//IntrBkSttlmAmt').text)
        s_code = root.find('.//DbtrAgt/FinInstnId/BICFI').text
        r_code = root.find('.//CdtrAgt/FinInstnId/BICFI').text
        net_positions[s_code] = net_positions.get(s_code, 0.0) - amount
        net_positions[r_code] = net_positions.get(r_code, 0.0) + amount

    can_resolve = True
    for bank_code, net_amount in net_positions.items():
        bank = db.query(Bank).filter(Bank.bank_code == bank_code).first()
        if bank and (bank.balance + net_amount) < -bank.debt_limit:
            can_resolve = False
            break

    if can_resolve:
        # Generowanie ID Sesji do raportowania
        session_id = f"SES-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        
        for bank_code, net_amount in net_positions.items():
            bank = db.query(Bank).filter(Bank.bank_code == bank_code).first()
            if bank:
                bank.balance += net_amount
                if bank.balance >= -bank.debt_limit:
                    bank.limit_exceeded_at = None
                    bank.status = "ACTIVE"
                    
                # ZAPIS RAPORTU DLA BANKU
                db.add(NettingReport(
                    session_id=session_id,
                    bank_code=bank_code,
                    net_position=net_amount,
                    status="SETTLED"
                ))
                    
        for xml_string in gridlock_queue:
            root = ET.fromstring(xml_string)
            amount = float(root.find('.//IntrBkSttlmAmt').text)
            s_code = root.find('.//DbtrAgt/FinInstnId/BICFI').text
            r_code = root.find('.//CdtrAgt/FinInstnId/BICFI').text
            db.add(Transaction(sender_code=s_code, receiver_code=r_code, amount=amount, status="RESOLVED"))

        db.commit()
        resolved_count = len(gridlock_queue)
        gridlock_queue.clear()
        return {"status": "SUCCESS", "message": f"Settled {resolved_count} queued transfers."}
    
    return {"status": "FAILED", "message": "Gridlock persists."}

@router.post("/central-bank/inject", tags=["Central Bank"])
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