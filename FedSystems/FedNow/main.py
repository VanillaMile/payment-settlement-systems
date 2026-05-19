from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()  # Load environment variables from .env file

# --- FRB Configuration ---
FRB_ROUTING_NUMBER = os.environ.get("FRB_ROUTING_NUMBER", "090000515")
FRB_LEGAL_NAME = os.environ.get("FRB_LEGAL_NAME", "Federal Reserve Bank")

fednow = FastAPI(title="FedNow API", version="1.0")

fednow.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@fednow.get("/health", tags=["Health"])
def health_check():
    return {"status": "FedNow API is healthy"}

@fednow.get("/frb-info", tags=["FRB"])
def get_frb_info():
    return {
        "routing_number": FRB_ROUTING_NUMBER,
        "legal_name": FRB_LEGAL_NAME
    }