import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Get database URL from .env, fallback to SQLite for easy dev
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./timetracker.db"  # fallback
)

# If using SQLite, need check_same_thread flag
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def create_tables():
    print(f"Creating tables with database: {DATABASE_URL}")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()