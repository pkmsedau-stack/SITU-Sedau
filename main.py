from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import databases
import sqlalchemy
import os
from datetime import datetime

# 1. Konfigurasi Database (Railway menyediakan DATABASE_URL otomatis)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost/situ_db")
database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# 2. Definisi Struktur Tabel (Schema)
pegawai = sqlalchemy.Table(
    "pegawai",
    metadata,
    sqlalchemy.Column("nip", sqlalchemy.String(18), primary_key=True),
    sqlalchemy.Column("nama", sqlalchemy.String),
    sqlalchemy.Column("jabatan_sekarang", sqlalchemy.String),
    sqlalchemy.Column("golongan_sekarang", sqlalchemy.String),
    sqlalchemy.Column("tmt_golongan", sqlalchemy.String),
    sqlalchemy.Column("tmt_berkala_terakhir", sqlalchemy.String),
    sqlalchemy.Column("profesi", sqlalchemy.String),
)

audit_logs = sqlalchemy.Table(
    "audit_logs",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.String, primary_key=True),
    sqlalchemy.Column("admin", sqlalchemy.String),
    sqlalchemy.Column("aktivitas", sqlalchemy.String),
    sqlalchemy.Column("timestamp", sqlalchemy.String),
)

# ... (Anda bisa menambah tabel surat dan tamu dengan pola yang sama)

app = FastAPI(title="SITU Puskesmas Sedau API")

# 3. Middleware CORS (PENTING: Agar Frontend bisa akses Backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Di produksi, ganti dengan URL frontend Anda
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    # Membuat tabel jika belum ada
    engine = sqlalchemy.create_engine(DATABASE_URL)
    metadata.create_all(engine)
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# --- ENDPOINT AUTH ---
@app.post("/api/v1/auth/login")
async def login(credentials: dict = Body(...)):
    nip = credentials.get("nip")
    pin = credentials.get("pin")
    # Mock Auth Sesuai Instruksi
    if nip == "199001012015031001" and pin == "123456":
        return {
            "nip": nip,
            "nama": "Admin Puskesmas",
            "role": "Admin",
            "accessToken": "mock-jwt-token-situ"
        }
    raise HTTPException(status_code=401, detail="NIP atau PIN salah")

# --- ENDPOINT PEGAWAI ---
@app.get("/api/v1/pegawai")
async def get_all_pegawai():
    query = pegawai.select()
    return await database.fetch_all(query)

@app.post("/api/v1/pegawai")
async def create_pegawai(data: dict):
    query = pegawai.insert().values(**data)
    await database.execute(query)
    return data

# --- ENDPOINT AUDIT ---
@app.get("/api/v1/audit")
async def get_audit():
    return await database.fetch_all(audit_logs.select().order_by(audit_logs.c.timestamp.desc()))

@app.post("/api/v1/audit")
async def add_audit(data: dict):
    log_id = f"log_{int(datetime.now().timestamp())}"
    new_log = {
        "id": log_id,
        "admin": "Admin", # Bisa diambil dari token nantinya
        "aktivitas": data.get("aktivitas"),
        "timestamp": datetime.now().isoformat()
    }
    await database.execute(audit_logs.insert().values(**new_log))
    return new_log