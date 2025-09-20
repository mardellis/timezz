# Add these routes to your backend/routes.py or create backend/trello_routes.py

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from db import get_db
from models import User, TimeEntry
from auth import create_access_token
import requests

router = APIRouter()

# Trello-specific models
class TrelloLoginRequest(BaseModel):
    email: str
    password: str
    trello_user_id: str
    trello_username: str
    trello_full_name: str

class TrelloBoardReportRequest(BaseModel):
    board_id: str
    days: Optional[int] = 30

# Trello authentication endpoint
@router.post("/auth/trello-login")
async def trello_login(request: TrelloLoginRequest, db: Session = Depends(get_db)):
    """Login specifically for Trello Power-Up users"""
    try:
        # Verify user credentials (you'll need to implement password verification)
        user = db.query(User).filter(User.email == request.email).first()
        
        if not user:
            # Create new user for Trello
            user = User(
                email=request.email,
                trello_id=request.trello_user_id,
                name=request.trello_full_name
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Update Trello info for existing user
            user.trello_id = request.trello_user_id
            user.name = request.trello_full_name
            db.commit()
        
        # Create access token
        access_token = create_access_token(request.trello_user_id)
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "trello_id": user.trello_id
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Board-specific reporting
@router.get("/reports/board/{board_id}")
async def get_board_report(
    board_id: str, 
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get time tracking report for a specific Trello board"""
    from datetime import datetime, timedelta
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Query entries for this board
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.board_id == board_id,
        TimeEntry.start_time >= start_date
    ).all()
    
    # Calculate totals
    total_minutes = sum(entry.duration_minutes or 0 for entry in entries)
    today_entries = [e for e in entries if e.start_time.date() == datetime.utcnow().date()]
    today_minutes = sum(entry.duration_minutes or 0 for entry in today_entries)
    
    week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    week_entries = [e for e in entries if e.start_time >= week_start]
    week_minutes = sum(entry.duration_minutes or 0 for entry in week_entries)
    
    return {
        "board_id": board_id,
        "period_days": days,
        "today_hours": today_minutes / 60,
        "week_hours": week_minutes / 60,
        "total_hours": total_minutes / 60,
        "total_entries": len(entries),
        "daily_average": (total_minutes / 60) / max(days, 1),
        "recent_entries": [
            {
                "id": entry.id,
                "card_id": entry.card_id,
                "card_name": entry.card_name,
                "duration_minutes": entry.duration_minutes,
                "created_at": entry.created_at.isoformat()
            }
            for entry in sorted(entries, key=lambda x: x.created_at, reverse=True)[:10]
        ]
    }

# Update CORS in main.py
"""
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://trello.com",
        "https://*.trellocdn.com", 
        "https://your-powerup-domain.com",
        "http://localhost:3000",  # Remove in production
        "http://localhost:8000"   # Remove in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
"""

# Enhanced time entry creation for Trello
@router.post("/time/entries/trello")
async def create_trello_time_entry(
    card_id: str,
    card_name: str,
    board_id: str,
    duration_minutes: float,
    description: Optional[str] = None,
    list_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create time entry specifically from Trello Power-Up"""
    
    entry = TimeEntry(
        user_id=current_user.id,
        card_id=card_id,
        card_name=card_name,
        board_id=board_id,
        list_name=list_name,
        duration_minutes=duration_minutes,
        description=description or f"Time tracked via Trello Power-Up",
        start_time=datetime.utcnow() - timedelta(minutes=duration_minutes),
        end_time=datetime.utcnow(),
        is_manual=True
    )
    
    db.add(entry)
    db.commit()
    db.refresh(entry)
    
    return {
        "id": entry.id,
        "duration_minutes": entry.duration_minutes,
        "card_name": entry.card_name,
        "created_at": entry.created_at.isoformat()
    }