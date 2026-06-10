from pydantic import BaseModel, field_validator
from typing import Optional
from services.xml_service import is_valid_rtn 

class BankCreate(BaseModel):
    bank_code: str
    routing_number: str
    balance: float = 0.0
    debt_limit: float = 0.0

    @field_validator('routing_number')
    @classmethod
    def validate_rtn(cls, v: str) -> str:
        if not is_valid_rtn(v):
            raise ValueError('Invalid RTN format or checksum failure')
        return v

class PaymentRequest(BaseModel):
    end_to_end_id: str
    amount: float
    currency: str = "USD"
    description: Optional[str] = None 
    sender_rtn: str  
    receiver_rtn: str 
    debtor_name: str
    debtor_account: str
    creditor_name: str
    creditor_account: str

    @field_validator('sender_rtn', 'receiver_rtn')
    @classmethod
    def validate_rtns(cls, v: str) -> str:
        if not is_valid_rtn(v):
            raise ValueError('Invalid RTN format or checksum failure')
        return v

class SettlementRequest(BaseModel):
    end_to_end_id: str
    status: str
    reason: str = ""

class LiquidityInjection(BaseModel):
    bank_code: str
    amount: float