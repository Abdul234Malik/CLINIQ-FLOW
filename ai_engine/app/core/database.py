"""AI Engine database configuration - Supabase connection."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

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
