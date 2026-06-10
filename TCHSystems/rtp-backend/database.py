import os
import secrets
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.sql import func

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rtp_user:rtp_password@postgres-rtp:5432/rtp_database")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Bank(Base):
    __tablename__ = "banks"
    bank_code = Column(String, primary_key=True, index=True)
    routing_number = Column(String, index=True, unique=True, nullable=True)
    balance = Column(Float, default=0.0)
    debt_limit = Column(Float, default=0.0)
    status = Column(String, default="ACTIVE")
    limit_exceeded_at = Column(DateTime(timezone=True), nullable=True)
    api_key = Column(String, unique=True, index=True)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sender_code = Column(String, index=True)
    receiver_code = Column(String, index=True)
    sender_rtn = Column(String, index=True, nullable=True)  
    receiver_rtn = Column(String, index=True, nullable=True)
    amount = Column(Float)
    status = Column(String) 
    message_id = Column(String, unique=True, nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    debtor_name = Column(String, nullable=True)          
    debtor_account = Column(String, nullable=True)               
    creditor_name = Column(String, nullable=True)            
    creditor_account = Column(String, nullable=True)            

class GridlockQueue(Base):
    __tablename__ = "gridlock_queue"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    xml_payload = Column(String) 
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class NettingReport(Base):
    __tablename__ = "netting_reports"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String)
    bank_code = Column(String, index=True)
    net_position = Column(Float)
    status = Column(String)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class MessageQueue(Base):
    __tablename__ = "message_queue"
    id = Column(Integer, primary_key=True, index=True)
    owner_bank_code = Column(String, ForeignKey("banks.bank_code"), index=True) 
    message_type = Column(String)
    message_id = Column(String, index=True)
    payload = Column(Text)
    status = Column(String, default="PENDING")
    created_at = Column(DateTime(timezone=True), default=func.now())

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Bank).count() == 0:
                    bank_a_key = os.getenv("BANKA_API_KEY", "keya") 
                    bank_b_key = os.getenv("BANKB_API_KEY", "keyb")
                    
                    db.add(Bank(bank_code="BANKA", balance=15000.0, debt_limit=50000.0, api_key=bank_a_key))
                    db.add(Bank(bank_code="BANKB", balance=12000.0, debt_limit=30000.0, api_key=bank_b_key))
                    db.commit()
    finally:
        db.close()