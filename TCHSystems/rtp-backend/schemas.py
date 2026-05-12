from pydantic import BaseModel

# Definiujemy, jakie dane będą potrzebne do zainicjowania zastrzyku płynności dla danego banku
class LiquidityInjection(BaseModel):
    bank_code: str
    amount: float