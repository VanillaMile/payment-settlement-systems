from sqlalchemy.orm import Session
from database import Bank, Transaction, NettingReport, GridlockQueue
from datetime import datetime, timezone
from services.xml_service import extract_rtp_data

def resolve_gridlock(db: Session):
    queue_items = db.query(GridlockQueue).all()
    if not queue_items: return

    net_positions = {}
    for item in queue_items:
        try:
            data = extract_rtp_data(item.xml_payload)
            net_positions[data["sender_code"]] = net_positions.get(data["sender_code"], 0.0) - data["amount"]
            net_positions[data["receiver_code"]] = net_positions.get(data["receiver_code"], 0.0) + data["amount"]
        except Exception: continue

    can_resolve = True
    for bank_code, net_amount in net_positions.items():
        bank = db.query(Bank).filter(Bank.bank_code == bank_code).first()
        if bank and (bank.balance + net_amount) < -bank.debt_limit:
            can_resolve = False
            break

    if can_resolve:
        session_id = f"SES-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        for bank_code, net_amount in net_positions.items():
            bank = db.query(Bank).filter(Bank.bank_code == bank_code).first()
            if bank:
                bank.balance += net_amount
                if bank.balance >= -bank.debt_limit:
                    bank.limit_exceeded_at = None
                    bank.status = "ACTIVE"
                db.add(NettingReport(session_id=session_id, bank_code=bank_code, net_position=net_amount, status="SETTLED"))
                    
        for item in queue_items:
            try:
                data = extract_rtp_data(item.xml_payload)
                e2e_id = data["end_to_end_id"]
                if not db.query(Transaction).filter(Transaction.message_id == e2e_id).first():
                    db.add(Transaction(
                        sender_code=data["sender_code"], receiver_code=data["receiver_code"], 
                        amount=data["amount"], status="RESOLVED", message_id=e2e_id,
                        debtor_name=data.get("debtor_name"), debtor_account=data.get("debtor_account"),
                        creditor_name=data.get("creditor_name"), creditor_account=data.get("creditor_account")
                    ))
            except Exception: pass
            db.delete(item)
        db.commit()