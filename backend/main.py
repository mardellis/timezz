from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import create_tables
from routes import router
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Trello Time Tracker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://trello.com",
        "https://*.trellocdn.com",
        "https://powerup.timezz.com",
        "https://app.timezz.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")

@app.on_event("startup")
async def startup():
    try:
        logger.info("Creating database tables...")
        create_tables()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        # Don't raise in production, just log
        pass

# Add health check endpoint
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.get("/")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)