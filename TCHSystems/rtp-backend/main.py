from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import router

# Automatyczne utworzenie tabel i dodanie banków (BANKA, BANKB)
init_db()

app = FastAPI(
    title="RTP System API",
    description="System rozrachunkowy czasu rzeczywistego RTP",
    version="2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/", tags=["Health"])
def read_root():
    return {"message": "System RTP działa"}