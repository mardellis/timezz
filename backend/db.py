import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load .env file if present
load_dotenv()

# Get database URL with proper fallback for Render
DATABASE_URL = os.getenv("DATABASE_URL")

# If no DATABASE_URL is set, try to construct from individual components
if not DATABASE_URL:
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432") 
    db_user = os.getenv("DB_USER", "timezz")
    db_password = os.getenv("DB_PASSWORD", "timezz123")
    db_name = os.getenv("DB_NAME", "timezz")
    
    DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

# Fallback to SQLite if PostgreSQL is not available
if DATABASE_URL.startswith("postgresql://localhost"):
    logger.warning("PostgreSQL not available, using SQLite fallback")
    DATABASE_URL = "sqlite:///./timetracker.db"

logger.info(f"Database URL: {DATABASE_URL}")

try:
    # Create engine with appropriate settings
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(DATABASE_URL)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    
    def create_tables():
        try:
            logger.info(f"Creating tables with database: {DATABASE_URL}")
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Tables created successfully!")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to create tables: {e}")
            return False
    
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
            
except Exception as e:
    logger.error(f"❌ Database initialization failed: {e}")
    
    # Create dummy functions for when database is not available
    def create_tables():
        logger.warning("⚠️ Database not available - running in demo mode")
        return False
    
    def get_db():
        logger.warning("⚠️ Database not available")
        return None
    
    Base = None
    engine = None
    SessionLocal = None
