import os
from fastapi import FastAPI
import databases
import sqlalchemy
from fastapi.middleware.cors import CORSMiddleware

# FIX: Railway memberikan postgresql://, tapi databases library butuh postgresql+asyncpg://
raw_uri = os.getenv("DATABASE_URL")
if raw_uri and raw_uri.startswith("postgresql://"):
    DATABASE_URL = raw_uri.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = raw_uri or "postgresql+asyncpg://postgres:password@localhost/situ_db"

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# ... (Definisi tabel tetap sama seperti sebelumnya) ...

app = FastAPI()

# Tambahkan CORS agar frontend tidak error
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    try:
        # Untuk inisialisasi tabel, kita pakai engine sinkron (tanpa +asyncpg)
        sync_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        engine = sqlalchemy.create_engine(sync_url)
        metadata.create_all(engine)
        
        # Connect ke database asinkron
        await database.connect()
        print("Successfully connected to Database")
    except Exception as e:
        print(f"Startup Error: {e}")
        # Jangan biarkan aplikasi crash diam-diam
        raise e

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# Tambahkan satu endpoint healthcheck untuk tes
@app.get("/")
async def health():
    return {"status": "online", "database": "connected"}

# ... (Endpoint lainnya) ...
