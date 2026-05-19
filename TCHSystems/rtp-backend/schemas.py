from pydantic import BaseModel

class BankCreate(BaseModel):
    bank_code: str
    balance: float = 0.0
    debt_limit: float = 0.0

# Definiujemy, jakie dane będą potrzebne do zainicjowania zastrzyku płynności dla danego banku
class LiquidityInjection(BaseModel):
    bank_code: str
    amount: float