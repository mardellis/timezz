from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, List
from db import get_db
from models import User, TimeEntry, Project, Client
from auth import get_current_user
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic models
class LoginRequest(BaseModel):
    trello_user_id: str
    trello_token: str
    name: Optional[str] = None
    email: Optional[str] = None

class StartTimerRequest(BaseModel):
    card_id: str
    card_name: str
    board_id: str
    list_name: Optional[str] = None
    description: Optional[str] = None

class ManualTimeEntryRequest(BaseModel):
    card_id: str
    card_name: str
    board_id: str
    duration_minutes: float
    description: Optional[str] = None
    list_name: Optional[str] = None

# Authentication routes
@router.post("/auth/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Handle Trello Power-Up authentication"""
    try:
        # Get or create user
        user = db.query(User).filter(User.trello_id == request.trello_user_id).first()
        
        if not user:
            user = User(
                trello_id=request.trello_user_id,
                email=request.email or f"{request.trello_user_id}@trello.local",
                name=request.name or "Trello User"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Update user info
            if request.name:
                user.name = request.name
            if request.email:
                user.email = request.email
            user.last_active = datetime.utcnow()
            db.commit()
        
        # Create access token
        from auth import create_access_token
        access_token = create_access_token(request.trello_user_id)
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "trello_id": user.trello_id,
                "subscription_tier": user.subscription_tier
            }
        }
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# Timer routes
@router.post("/time/start")
async def start_timer(
    request: StartTimerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new timer"""
    try:
        # Check if user has an active timer
        active_timer = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.is_(None)
        ).first()
        
        if active_timer:
            # Stop the existing timer
            active_timer.end_time = datetime.utcnow()
            duration = (active_timer.end_time - active_timer.start_time).total_seconds() / 60
            active_timer.duration_minutes = duration
            db.commit()
        
        # Create new timer
        new_timer = TimeEntry(
            user_id=current_user.id,
            card_id=request.card_id,
            card_name=request.card_name,
            board_id=request.board_id,
            list_name=request.list_name,
            description=request.description or f"Timer started for: {request.card_name}",
            start_time=datetime.utcnow(),
            is_manual=False
        )
        
        db.add(new_timer)
        db.commit()
        db.refresh(new_timer)
        
        return {
            "id": new_timer.id,
            "card_id": new_timer.card_id,
            "card_name": new_timer.card_name,
            "start_time": new_timer.start_time.isoformat(),
            "message": "Timer started successfully"
        }
    except Exception as e:
        logger.error(f"Start timer error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/time/stop")
async def stop_timer(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stop the active timer"""
    try:
        # Find active timer
        active_timer = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.is_(None)
        ).first()
        
        if not active_timer:
            raise HTTPException(status_code=404, detail="No active timer found")
        
        # Stop timer
        active_timer.end_time = datetime.utcnow()
        duration = (active_timer.end_time - active_timer.start_time).total_seconds() / 60
        active_timer.duration_minutes = duration
        
        # Calculate amount if hourly rate is set
        if current_user.hourly_rate:
            active_timer.hourly_rate = current_user.hourly_rate
            active_timer.amount = (duration / 60) * current_user.hourly_rate
        
        db.commit()
        db.refresh(active_timer)
        
        return {
            "id": active_timer.id,
            "duration_minutes": active_timer.duration_minutes,
            "duration_hours": round(duration / 60, 2),
            "card_name": active_timer.card_name,
            "amount": active_timer.amount,
            "message": f"Timer stopped. Duration: {round(duration / 60, 2)} hours"
        }
    except Exception as e:
        logger.error(f"Stop timer error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/time/active")
async def get_active_timer(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get currently active timer"""
    try:
        active_timer = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.is_(None)
        ).first()
        
        if not active_timer:
            return {"active": False, "timer": None}
        
        # Calculate current duration
        current_duration = (datetime.utcnow() - active_timer.start_time).total_seconds() / 60
        
        return {
            "active": True,
            "timer": {
                "id": active_timer.id,
                "card_id": active_timer.card_id,
                "card_name": active_timer.card_name,
                "board_id": active_timer.board_id,
                "start_time": active_timer.start_time.isoformat(),
                "duration_minutes": current_duration,
                "description": active_timer.description
            }
        }
    except Exception as e:
        logger.error(f"Get active timer error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# Manual time entry
@router.post("/time/entries/manual")
async def create_manual_entry(
    request: ManualTimeEntryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create manual time entry"""
    try:
        entry = TimeEntry(
            user_id=current_user.id,
            card_id=request.card_id,
            card_name=request.card_name,
            board_id=request.board_id,
            list_name=request.list_name,
            duration_minutes=request.duration_minutes,
            description=request.description or f"Manual entry for: {request.card_name}",
            start_time=datetime.utcnow() - timedelta(minutes=request.duration_minutes),
            end_time=datetime.utcnow(),
            is_manual=True
        )
        
        # Calculate amount if hourly rate is set
        if current_user.hourly_rate:
            entry.hourly_rate = current_user.hourly_rate
            entry.amount = (request.duration_minutes / 60) * current_user.hourly_rate
        
        db.add(entry)
        db.commit()
        db.refresh(entry)
        
        return {
            "id": entry.id,
            "duration_minutes": entry.duration_minutes,
            "duration_hours": round(entry.duration_minutes / 60, 2),
            "card_name": entry.card_name,
            "amount": entry.amount,
            "created_at": entry.created_at.isoformat()
        }
    except Exception as e:
        logger.error(f"Manual entry error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# Get time entries
@router.get("/time/entries")
async def get_time_entries(
    limit: int = 50,
    board_id: Optional[str] = None,
    days: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's time entries"""
    try:
        query = db.query(TimeEntry).filter(TimeEntry.user_id == current_user.id)
        
        if board_id:
            query = query.filter(TimeEntry.board_id == board_id)
        
        if days:
            start_date = datetime.utcnow() - timedelta(days=days)
            query = query.filter(TimeEntry.created_at >= start_date)
        
        entries = query.order_by(TimeEntry.created_at.desc()).limit(limit).all()
        
        return [{
            "id": entry.id,
            "card_id": entry.card_id,
            "card_name": entry.card_name,
            "board_id": entry.board_id,
            "list_name": entry.list_name,
            "duration_minutes": entry.duration_minutes,
            "duration_hours": round((entry.duration_minutes or 0) / 60, 2),
            "description": entry.description,
            "amount": entry.amount,
            "is_manual": entry.is_manual,
            "is_billable": entry.is_billable,
            "created_at": entry.created_at.isoformat(),
            "start_time": entry.start_time.isoformat() if entry.start_time else None,
            "end_time": entry.end_time.isoformat() if entry.end_time else None
        } for entry in entries]
    except Exception as e:
        logger.error(f"Get entries error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# Reports
@router.get("/reports/detailed")
async def get_detailed_report(
    days: int = 30,
    board_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed time tracking report"""
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Base query
        query = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.created_at >= start_date
        )
        
        if board_id:
            query = query.filter(TimeEntry.board_id == board_id)
        
        entries = query.all()
        
        # Calculate totals
        total_minutes = sum(entry.duration_minutes or 0 for entry in entries)
        total_hours = total_minutes / 60
        total_amount = sum(entry.amount or 0 for entry in entries)
        
        # Today's stats
        today = datetime.utcnow().date()
        today_entries = [e for e in entries if e.created_at.date() == today]
        today_minutes = sum(entry.duration_minutes or 0 for entry in today_entries)
        
        # This week's stats
        week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
        week_entries = [e for e in entries if e.created_at >= week_start]
        week_minutes = sum(entry.duration_minutes or 0 for entry in week_entries)
        
        # Group by board
        board_stats = {}
        for entry in entries:
            if entry.board_id not in board_stats:
                board_stats[entry.board_id] = {
                    "board_id": entry.board_id,
                    "total_minutes": 0,
                    "total_entries": 0,
                    "total_amount": 0
                }
            board_stats[entry.board_id]["total_minutes"] += entry.duration_minutes or 0
            board_stats[entry.board_id]["total_entries"] += 1
            board_stats[entry.board_id]["total_amount"] += entry.amount or 0
        
        return {
            "period_days": days,
            "total_hours": round(total_hours, 2),
            "total_minutes": total_minutes,
            "total_entries": len(entries),
            "total_amount": round(total_amount, 2),
            "today_hours": round(today_minutes / 60, 2),
            "week_hours": round(week_minutes / 60, 2),
            "daily_average": round(total_hours / max(days, 1), 2),
            "board_breakdown": list(board_stats.values()),
            "recent_entries": [
                {
                    "id": entry.id,
                    "card_name": entry.card_name,
                    "duration_hours": round((entry.duration_minutes or 0) / 60, 2),
                    "created_at": entry.created_at.isoformat()
                }
                for entry in sorted(entries, key=lambda x: x.created_at, reverse=True)[:10]
            ]
        }
    except Exception as e:
        logger.error(f"Report error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/reports/board/{board_id}")
async def get_board_report(
    board_id: str,
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get report for specific board"""
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        entries = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.board_id == board_id,
            TimeEntry.created_at >= start_date
        ).all()
        
        total_minutes = sum(entry.duration_minutes or 0 for entry in entries)
        
        # Today's entries
        today = datetime.utcnow().date()
        today_entries = [e for e in entries if e.created_at.date() == today]
        today_minutes = sum(entry.duration_minutes or 0 for entry in today_entries)
        
        # This week's entries
        week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
        week_entries = [e for e in entries if e.created_at >= week_start]
        week_minutes = sum(entry.duration_minutes or 0 for entry in week_entries)
        
        return {
            "board_id": board_id,
            "period_days": days,
            "today_hours": round(today_minutes / 60, 2),
            "week_hours": round(week_minutes / 60, 2),
            "total_hours": round(total_minutes / 60, 2),
            "total_entries": len(entries),
            "daily_average": round((total_minutes / 60) / max(days, 1), 2),
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
    except Exception as e:
        logger.error(f"Board report error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# User profile
@router.get("/user/profile")
async def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user profile"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "trello_id": current_user.trello_id,
        "subscription_tier": current_user.subscription_tier,
        "hourly_rate": current_user.hourly_rate,
        "currency": current_user.currency,
        "created_at": current_user.created_at.isoformat()
    }