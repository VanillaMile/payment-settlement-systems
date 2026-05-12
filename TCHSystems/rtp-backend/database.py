import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://rtp_user:rtp_password@postgres-rtp:5432/rtp_database")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Bank(Base):
    __tablename__ = "banks"
    bank_code = Column(String, primary_key=True, index=True)
    balance = Column(Float, default=0.0)
    debt_limit = Column(Float, default=0.0)
    status = Column(String, default="ACTIVE")
    limit_exceeded_at = Column(DateTime(timezone=True), nullable=True)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sender_code = Column(String, index=True)
    receiver_code = Column(String, index=True)
    amount = Column(Float)
    status = Column(String) 
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# Tabela raportów z sesji nettingowych
class NettingReport(Base):
    __tablename__ = "netting_reports"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(String) # Identyfikator sesji
    bank_code = Column(String, index=True)
    net_position = Column(Float) # Kwota netto: dodatnia = bank otrzymuje, ujemna = bank płaci
    status = Column(String) # np. SETTLED
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

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
            db.add(Bank(bank_code="BANKA", balance=15000.0, debt_limit=50000.0))
            db.add(Bank(bank_code="BANKB", balance=12000.0, debt_limit=30000.0))
            db.commit()
    finally:
        db.close()