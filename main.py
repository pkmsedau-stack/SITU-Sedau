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
raw_uri = os.getenv("DATABASE_URL", "").strip()

if not raw_uri:
    print("WARNING: DATABASE_URL tidak ditemukan, menggunakan SQLite untuk fallback (Hanya untuk testing local!)")
    DATABASE_URL = "sqlite:///./test.db"
    SYNC_DATABASE_URL = DATABASE_URL
else:
    # 1. Perbaiki Protokol untuk Driver ASINKRON (asyncpg)
    if raw_uri.startswith("postgres://"):
        async_uri = raw_uri.replace("postgres://", "postgresql+asyncpg://", 1)
    elif raw_uri.startswith("postgresql://"):
        async_uri = raw_uri.replace("postgresql://", "postgresql+asyncpg://", 1)
    else:
        async_uri = raw_uri

    # 2. Tambahkan SSL Mode jika belum ada (Wajib untuk Cloud DB)
    if "sslmode" not in async_uri:
        connector = "&" if "?" in async_uri else "?"
        async_uri += f"{connector}sslmode=require"
    
    DATABASE_URL = async_uri
    # URL Sinkron untuk SQLAlchemy create_all (psycopg2)
    SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

print(f"DATABASE_URL (Masked): {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'Local/SQLite'}")

# Inisialisasi Database asinkron
# Jika di cloud, kita paksa penggunaan SSL melalui argument
database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# --- DEFINISI TABEL ---
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

audit_logs = sqlalchemy.Table(
    "audit_logs",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.String, primary_key=True),
    sqlalchemy.Column("admin", sqlalchemy.String),
    sqlalchemy.Column("aktivitas", sqlalchemy.String),
    sqlalchemy.Column("timestamp", sqlalchemy.String),
)

# --- APP INITIALIZATION ---
app = FastAPI(title="SITU Backend v2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    print("Startup: Memulai inisialisasi aplikasi...")
    try:
        # Step 1: Inisialisasi Tabel (Sinkron)
        print("Startup: Mencoba membuat tabel (SQLAlchemy Sync)...")
        engine = sqlalchemy.create_engine(
            SYNC_DATABASE_URL, 
            connect_args={"connect_timeout": 10} # Timeout agar tidak hang selamanya
        )
        metadata.create_all(engine)
        print("Startup: Tabel berhasil diverifikasi/dibuat.")
        
        # Step 2: Connect Asinkron
        print("Startup: Menghubungkan database asinkron (databases + asyncpg)...")
        await database.connect()
        print("Startup: DATABASE CONNECTED SUCCESSFULLY.")
    except Exception as e:
        print(f"STARTUP CRITICAL ERROR: {type(e).__name__} - {e}")
        # Jangan biarkan aplikasi hang, biarkan lanjut tapi log error-nya jelas
        pass

@app.on_event("shutdown")
async def shutdown():
    if database.is_connected:
        await database.disconnect()
        print("Shutdown: Database disconnected.")

# --- MODELS ---
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

class AuditIn(BaseModel):
    aktivitas: str

# --- ENDPOINTS ---
@app.get("/api/v1/health")
async def health():
    return {
        "status": "online",
        "database": "connected" if database.is_connected else "error",
        "environment": "railway" if os.getenv("RAILWAY_ENVIRONMENT") else "local"
    }

@app.get("/api/v1/pegawai")
async def get_pegawai():
    if not database.is_connected:
        raise HTTPException(status_code=503, detail="Database connection is not active.")
    query = pegawai.select()
    return await database.fetch_all(query)

@app.post("/api/v1/pegawai")
async def create_pegawai(data: PegawaiIn):
    item_id = str(uuid.uuid4())
    query = pegawai.insert().values(id=item_id, **data.dict())
    await database.execute(query)
    return {**data.dict(), "id": item_id}

@app.post("/api/v1/audit")
async def create_audit(data: AuditIn):
    item_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    query = audit_logs.insert().values(id=item_id, admin="Admin", aktivitas=data.aktivitas, timestamp=now)
    await database.execute(query)
    return {"id": item_id, "admin": "Admin", "aktivitas": data.aktivitas, "timestamp": now}

@app.get("/")
async def root():
    return {"message": "SITU API is Running", "docs": "/docs"}
