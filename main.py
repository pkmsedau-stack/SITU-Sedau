
import os
import uuid
import databases
import sqlalchemy
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime

# --- KONFIGURASI DATABASE ---
raw_uri = os.getenv("DATABASE_URL")

if not raw_uri:
    # Fallback untuk pengembangan lokal
    DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost/situ_db"
else:
    # 1. Transformasi protokol untuk library 'databases' asinkron
    if raw_uri.startswith("postgres://"):
        DATABASE_URL = raw_uri.replace("postgres://", "postgresql+asyncpg://", 1)
    elif raw_uri.startswith("postgresql://"):
        DATABASE_URL = raw_uri.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        DATABASE_URL = raw_uri

    # 2. PAKSA mode SSL (Wajib untuk Railway PostgreSQL)
    if "sslmode" not in DATABASE_URL:
        connector = "&" if "?" in DATABASE_URL else "?"
        DATABASE_URL += f"{connector}sslmode=require"

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# --- DEFINISI TABEL ---

# 1. Tabel Pegawai
pegawai = sqlalchemy.Table(
    "pegawai",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.String, primary_key=True),
    sqlalchemy.Column("nip", sqlalchemy.String, unique=True, index=True),
    sqlalchemy.Column("nama", sqlalchemy.String),
    sqlalchemy.Column("jabatan_sekarang", sqlalchemy.String),
    sqlalchemy.Column("tmt_jabatan", sqlalchemy.String),
    sqlalchemy.Column("golongan_sekarang", sqlalchemy.String),
    sqlalchemy.Column("tmt_golongan", sqlalchemy.String),
    sqlalchemy.Column("tmt_berkala_terakhir", sqlalchemy.String),
    sqlalchemy.Column("profesi", sqlalchemy.String),
    sqlalchemy.Column("status_ukom", sqlalchemy.String, default="Tidak Wajib"),
    sqlalchemy.Column("mkg_tahun", sqlalchemy.Integer, default=0),
    sqlalchemy.Column("mkg_bulan", sqlalchemy.Integer, default=0),
)

# 2. Tabel Buku Tamu
guests = sqlalchemy.Table(
    "guests",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.String, primary_key=True),
    sqlalchemy.Column("tanggal", sqlalchemy.String),
    sqlalchemy.Column("nama", sqlalchemy.String),
    sqlalchemy.Column("instansi", sqlalchemy.String),
    sqlalchemy.Column("noHp", sqlalchemy.String),
    sqlalchemy.Column("keperluan", sqlalchemy.String),
    sqlalchemy.Column("tujuanNip", sqlalchemy.String),
    sqlalchemy.Column("tujuanNama", sqlalchemy.String),
    sqlalchemy.Column("status", sqlalchemy.String, default="Menunggu"),
)

# 3. Tabel Audit Log
audit_logs = sqlalchemy.Table(
    "audit_logs",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.String, primary_key=True),
    sqlalchemy.Column("admin", sqlalchemy.String),
    sqlalchemy.Column("aktivitas", sqlalchemy.String),
    sqlalchemy.Column("timestamp", sqlalchemy.String),
)

# 4. Tabel Settings TU
settings = sqlalchemy.Table(
    "settings",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.Integer, primary_key=True),
    sqlalchemy.Column("namaPuskesmas", sqlalchemy.String),
    sqlalchemy.Column("namaKepala", sqlalchemy.String),
    sqlalchemy.Column("nipKepala", sqlalchemy.String),
    sqlalchemy.Column("jabatanKepala", sqlalchemy.String),
    sqlalchemy.Column("formatNomor", sqlalchemy.String),
)

# --- MODELS (PYDANTIC) ---
class PegawaiIn(BaseModel):
    nip: str
    nama: str
    jabatan_sekarang: str
    tmt_jabatan: str
    golongan_sekarang: str
    tmt_golongan: str
    tmt_berkala_terakhir: str
    profesi: str
    status_ukom: Optional[str] = "Tidak Wajib"
    mkg_tahun: Optional[int] = 0
    mkg_bulan: Optional[int] = 0

class LoginIn(BaseModel):
    nip: str
    pin: str

class AuditIn(BaseModel):
    aktivitas: str

# --- APP INITIALIZATION ---
app = FastAPI(title="SITU Backend - Railway Pro")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    try:
        # Inisialisasi tabel menggunakan engine sinkron (tanpa +asyncpg)
        sync_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        engine = sqlalchemy.create_engine(sync_url)
        metadata.create_all(engine)
        
        # Connect ke database asinkron
        await database.connect()
        print("Backend: Berhasil terhubung ke PostgreSQL Railway")
    except Exception as e:
        print(f"CRITICAL ERROR (DB): {e}")
        # Tetap jalankan app agar healthcheck bisa diakses dari frontend
        pass

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# --- ENDPOINTS ---

@app.get("/api/v1/health")
async def health():
    db_status = "connected" if database.is_connected else "disconnected"
    return {
        "status": "online",
        "database": db_status,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/v1/auth/login")
async def login(data: LoginIn):
    # Simulasi login (Di produksi gunakan hash password/PIN)
    if data.pin == "123456" or data.nip == "197801012005011002":
        return {
            "nip": data.nip,
            "nama": "Administrator SITU",
            "role": "Admin",
            "accessToken": str(uuid.uuid4())
        }
    raise HTTPException(status_code=401, detail="NIP atau PIN salah.")

# Pegawai CRUD
@app.get("/api/v1/pegawai")
async def get_pegawai():
    query = pegawai.select()
    return await database.fetch_all(query)

@app.post("/api/v1/pegawai")
async def create_pegawai(data: PegawaiIn):
    item_id = str(uuid.uuid4())
    query = pegawai.insert().values(id=item_id, **data.dict())
    await database.execute(query)
    return {**data.dict(), "id": item_id}

@app.put("/api/v1/pegawai/{nip}")
async def update_pegawai(nip: str, data: PegawaiIn):
    query = pegawai.update().where(pegawai.c.nip == nip).values(**data.dict())
    await database.execute(query)
    return data

@app.delete("/api/v1/pegawai/{nip}")
async def delete_pegawai(nip: str):
    query = pegawai.delete().where(pegawai.c.nip == nip)
    await database.execute(query)
    return {"status": "deleted"}

# Audit Log
@app.get("/api/v1/audit")
async def get_audit():
    query = audit_logs.select().order_by(audit_logs.c.timestamp.desc())
    return await database.fetch_all(query)

@app.post("/api/v1/audit")
async def create_audit(data: AuditIn):
    item_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    query = audit_logs.insert().values(
        id=item_id, 
        admin="Admin", 
        aktivitas=data.aktivitas, 
        timestamp=now
    )
    await database.execute(query)
    return {"id": item_id, "admin": "Admin", "aktivitas": data.aktivitas, "timestamp": now}

# e-Tamu CRUD
@app.get("/api/v1/guests")
async def get_guests():
    query = guests.select().order_by(guests.c.tanggal.desc())
    return await database.fetch_all(query)

@app.post("/api/v1/guests")
async def create_guest(data: dict):
    item_id = str(uuid.uuid4())
    query = guests.insert().values(id=item_id, **data)
    await database.execute(query)
    return {**data, "id": item_id}

@app.patch("/api/v1/guests/{id}/status")
async def update_guest_status(id: str, data: dict):
    query = guests.update().where(guests.c.id == id).values(status=data['status'])
    await database.execute(query)
    return {"status": "updated"}

# Root redirect ke health
@app.get("/")
async def root():
    return {"app": "SITU Backend", "version": "2.0", "docs": "/docs"}
