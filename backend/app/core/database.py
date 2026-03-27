from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# Legacy fallback logic kept for reference:
# DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_LOCAL")
# if not DATABASE_URL:
#     base = Path(__file__).resolve().parents[2]
#     data_dir = base / "data"
#     data_dir.mkdir(parents=True, exist_ok=True)
#     DATABASE_URL = f"sqlite:///{data_dir / 'cliniq_flow.db'}"

DATABASE_URL = os.getenv("DATABASE_URL_SUPABASE") or os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Supabase DATABASE_URL_SUPABASE (or DATABASE_URL) is required")

# Prefer psycopg driver if URL omits explicit postgres dialect driver.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

if "supabase" not in DATABASE_URL.lower():
    raise ValueError("Database URL must point to Supabase")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
