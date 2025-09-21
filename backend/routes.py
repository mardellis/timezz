from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from db import get_db
from models import User, TimeEntry, Project, Client
from auth import get_current_user, get_current_user_optional, create_access_token
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Enhanced Pydantic models
class LoginRequest(BaseModel):
    trello_user_id: str
    trello_token: Optional[str] = None
    name: Optional[str] = None
    email: Optional[EmailStr] = None

class StartTimerRequest(BaseModel):
    card_id: str
    card_name: str
    board_id: str
    list_name: Optional[str] = None
    description: Optional[str] = None

class StopTimerRequest(BaseModel):
    save_entry: bool = True

class ManualTimeEntryRequest(BaseModel):
    card_id: str
    card_name: str
    board_id: str
    duration_minutes: float
    description: Optional[str] = None
    list_name: Optional[str] = None
    date: Optional[str] = None  # ISO date string

class UpdateTimeEntryRequest(BaseModel):
    description: Optional[str] = None
    duration_minutes: Optional[float] = None
    is_billable: Optional[bool] = None

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    hourly_rate: Optional[float] = None
    currency: Optional[str] = None

# Authentication routes
@router.post("/auth/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Enhanced Trello Power-Up authentication"""
    try:
        logger.info(f"Login attempt for user: {request.trello_user_id}")
        
        # If database is not available, return demo token
        if db is None:
            access_token = create_access_token(request.trello_user_id)
            return {
                "access_token": access_token,
                "token_type": "bearer",
                "user": {
                    "id": hash(request.trello_user_id) % 1000000,
                    "email": request.email or f"{request.trello_user_id}@demo.local",
                    "name": request.name or "Demo User",
                    "trello_id": request.trello_user_id,
                    "subscription_tier": "free",
                    "demo_mode": True
                }
            }
        
        # Get or create user
        user = db.query(User).filter(User.trello_id == request.trello_user_id).first()
        
        if not user:
            logger.info(f"Creating new user: {request.trello_user_id}")
            user = User(
                trello_id=request.trello_user_id,
                email=request.email or f"{request.trello_user_id}@trello.local",
                name=request.name or "Trello User"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Update user info if provided
            if request.name and request.name != user.name:
                user.name = request.name
            if request.email and request.email != user.email:
                user.email = request.email
            user.last_active = datetime.utcnow()
            db.commit()
        
        # Create access token
        access_token = create_access_token(request.trello_user_id)
        
        logger.info(f"Login successful for user: {user.email}")
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "trello_id": user.trello_id,
                "subscription_tier": user.subscription_tier,
                "hourly_rate": user.hourly_rate,
                "currency": user.currency
            }
        }
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=400, detail=f"Login failed: {str(e)}")

@router.post("/auth/refresh")
async def refresh_token(current_user = Depends(get_current_user)):
    """Refresh access token"""
    try:
        new_token = create_access_token(current_user.trello_id)
        return {
            "access_token": new_token,
            "token_type": "bearer",
            "message": "Token refreshed successfully"
        }
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(status_code=400, detail="Failed to refresh token")

# Timer routes with enhanced error handling
@router.post("/time/start")
async def start_timer(
    request: StartTimerRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new timer with improved logic"""
    try:
        logger.info(f"Starting timer for card: {request.card_name} by user: {getattr(current_user, 'email', 'demo')}")
        
        # Demo mode handling
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            logger.info("Demo mode: Timer started")
            return {
                "id": f"demo_{int(datetime.utcnow().timestamp())}",
                "card_id": request.card_id,
                "card_name": request.card_name,
                "start_time": datetime.utcnow().isoformat(),
                "message": "Timer started successfully (demo mode)",
                "demo_mode": True
            }
        
        # Check if user has an active timer
        active_timer = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.is_(None)
        ).first()
        
        if active_timer:
            logger.info(f"Stopping existing timer: {active_timer.id}")
            # Stop the existing timer
            active_timer.end_time = datetime.utcnow()
            duration = (active_timer.end_time - active_timer.start_time).total_seconds() / 60
            active_timer.duration_minutes = duration
            
            # Calculate amount if hourly rate is set
            if current_user.hourly_rate and active_timer.is_billable:
                active_timer.hourly_rate = current_user.hourly_rate
                active_timer.amount = (duration / 60) * current_user.hourly_rate
            
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
            is_manual=False,
            is_billable=True
        )
        
        db.add(new_timer)
        db.commit()
        db.refresh(new_timer)
        
        logger.info(f"Timer started successfully: {new_timer.id}")
        return {
            "id": new_timer.id,
            "card_id": new_timer.card_id,
            "card_name": new_timer.card_name,
            "board_id": new_timer.board_id,
            "start_time": new_timer.start_time.isoformat(),
            "message": "Timer started successfully"
        }
        
    except Exception as e:
        logger.error(f"Start timer error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start timer: {str(e)}")

@router.post("/time/stop")
async def stop_timer(
    request: Optional[StopTimerRequest] = None,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stop the active timer with enhanced logic"""
    try:
        logger.info(f"Stopping timer for user: {getattr(current_user, 'email', 'demo')}")
        
        # Demo mode handling
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            logger.info("Demo mode: Timer stopped")
            return {
                "id": "demo_timer",
                "duration_minutes": 25.5,
                "duration_hours": 0.43,
                "card_name": "Demo Card",
                "amount": 21.25,
                "message": "Timer stopped successfully (demo mode)",
                "demo_mode": True
            }
        
        # Find active timer
        active_timer = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.is_(None)
        ).first()
        
        if not active_timer:
            raise HTTPException(status_code=404, detail="No active timer found")
        
        # Stop timer
        active_timer.end_time = datetime.utcnow()
        duration_seconds = (active_timer.end_time - active_timer.start_time).total_seconds()
        duration_minutes = duration_seconds / 60
        active_timer.duration_minutes = duration_minutes
        
        # Calculate amount if hourly rate is set and entry is billable
        amount = 0
        if current_user.hourly_rate and active_timer.is_billable:
            active_timer.hourly_rate = current_user.hourly_rate
            amount = (duration_minutes / 60) * current_user.hourly_rate
            active_timer.amount = amount
        
        # Save if requested (default True)
        save_entry = request.save_entry if request else True
        if save_entry:
            db.commit()
            db.refresh(active_timer)
        else:
            # Delete the timer entry
            db.delete(active_timer)
            db.commit()
        
        logger.info(f"Timer stopped: {duration_minutes:.2f} minutes")
        return {
            "id": active_timer.id,
            "duration_minutes": round(duration_minutes, 2),
            "duration_hours": round(duration_minutes / 60, 2),
            "card_name": active_timer.card_name,
            "amount": round(amount, 2) if amount else None,
            "saved": save_entry,
            "message": f"Timer stopped. Duration: {round(duration_minutes / 60, 2)} hours"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stop timer error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop timer: {str(e)}")

@router.get("/time/active")
async def get_active_timer(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get currently active timer"""
    try:
        # Demo mode handling
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            return {"active": False, "timer": None, "demo_mode": True}
        
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
                "list_name": active_timer.list_name,
                "start_time": active_timer.start_time.isoformat(),
                "duration_minutes": round(current_duration, 2),
                "description": active_timer.description,
                "is_billable": active_timer.is_billable
            }
        }
    except Exception as e:
        logger.error(f"Get active timer error: {e}")
        return {"active": False, "timer": None, "error": str(e)}

# Enhanced time entry management
@router.post("/time/entries/manual")
async def create_manual_entry(
    request: ManualTimeEntryRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create manual time entry with date support"""
    try:
        logger.info(f"Creating manual entry for card: {request.card_name}")
        
        # Demo mode handling
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            return {
                "id": f"demo_manual_{int(datetime.utcnow().timestamp())}",
                "duration_minutes": request.duration_minutes,
                "duration_hours": round(request.duration_minutes / 60, 2),
                "card_name": request.card_name,
                "amount": round((request.duration_minutes / 60) * 50, 2),
                "created_at": datetime.utcnow().isoformat(),
                "demo_mode": True
            }
        
        # Parse date if provided
        entry_date = datetime.utcnow()
        if request.date:
            try:
                entry_date = datetime.fromisoformat(request.date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(400, "Invalid date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)")
        
        entry = TimeEntry(
            user_id=current_user.id,
            card_id=request.card_id,
            card_name=request.card_name,
            board_id=request.board_id,
            list_name=request.list_name,
            duration_minutes=request.duration_minutes,
            description=request.description or f"Manual entry for: {request.card_name}",
            start_time=entry_date - timedelta(minutes=request.duration_minutes),
            end_time=entry_date,
            is_manual=True,
            is_billable=True,
            created_at=entry_date
        )
        
        # Calculate amount if hourly rate is set
        amount = 0
        if current_user.hourly_rate:
            entry.hourly_rate = current_user.hourly_rate
            amount = (request.duration_minutes / 60) * current_user.hourly_rate
            entry.amount = amount
        
        db.add(entry)
        db.commit()
        db.refresh(entry)
        
        logger.info(f"Manual entry created: {entry.id}")
        return {
            "id": entry.id,
            "duration_minutes": entry.duration_minutes,
            "duration_hours": round(entry.duration_minutes / 60, 2),
            "card_name": entry.card_name,
            "amount": round(amount, 2) if amount else None,
            "created_at": entry.created_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Manual entry error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create manual entry: {str(e)}")

@router.get("/time/entries")
async def get_time_entries(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    board_id: Optional[str] = None,
    card_id: Optional[str] = None,
    days: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's time entries with advanced filtering"""
    try:
        # Demo mode handling
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            demo_entries = [
                {
                    "id": 1,
                    "card_id": "demo_card_1",
                    "card_name": "Fix login issues",
                    "board_id": "demo_board",
                    "list_name": "In Progress",
                    "duration_minutes": 90,
                    "duration_hours": 1.5,
                    "description": "Fixed authentication bug",
                    "amount": 75.0,
                    "is_manual": False,
                    "is_billable": True,
                    "created_at": datetime.utcnow().isoformat(),
                    "start_time": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                    "end_time": (datetime.utcnow() - timedelta(minutes=30)).isoformat()
                }
            ]
            return {"entries": demo_entries, "total": 1, "demo_mode": True}
        
        query = db.query(TimeEntry).filter(TimeEntry.user_id == current_user.id)
        
        # Apply filters
        if board_id:
            query = query.filter(TimeEntry.board_id == board_id)
        
        if card_id:
            query = query.filter(TimeEntry.card_id == card_id)
        
        if days:
            start_date_filter = datetime.utcnow() - timedelta(days=days)
            query = query.filter(TimeEntry.created_at >= start_date_filter)
        
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                query = query.filter(TimeEntry.created_at >= start_dt)
            except ValueError:
                raise HTTPException(400, "Invalid start_date format")
        
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                query = query.filter(TimeEntry.created_at <= end_dt)
            except ValueError:
                raise HTTPException(400, "Invalid end_date format")
        
        # Get total count for pagination
        total = query.count()
        
        # Apply pagination and ordering
        entries = query.order_by(desc(TimeEntry.created_at)).offset(offset).limit(limit).all()
        
        return {
            "entries": [
                {
                    "id": entry.id,
                    "card_id": entry.card_id,
                    "card_name": entry.card_name,
                    "board_id": entry.board_id,
                    "list_name": entry.list_name,
                    "duration_minutes": entry.duration_minutes,
                    "duration_hours": round((entry.duration_minutes or 0) / 60, 2),
                    "description": entry.description,
                    "amount": entry.amount,
                    "hourly_rate": entry.hourly_rate,
                    "is_manual": entry.is_manual,
                    "is_billable": entry.is_billable,
                    "is_billed": entry.is_billed,
                    "created_at": entry.created_at.isoformat(),
                    "start_time": entry.start_time.isoformat() if entry.start_time else None,
                    "end_time": entry.end_time.isoformat() if entry.end_time else None
                } for entry in entries
            ],
            "total": total,
            "limit": limit,
            "offset": offset
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get entries error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get time entries: {str(e)}")

@router.put("/time/entries/{entry_id}")
async def update_time_entry(
    entry_id: int,
    request: UpdateTimeEntryRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a time entry"""
    try:
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            return {
                "id": entry_id,
                "message": "Entry updated successfully (demo mode)",
                "demo_mode": True
            }
        
        entry = db.query(TimeEntry).filter(
            TimeEntry.id == entry_id,
            TimeEntry.user_id == current_user.id
        ).first()
        
        if not entry:
            raise HTTPException(404, "Time entry not found")
        
        # Update fields
        if request.description is not None:
            entry.description = request.description
        
        if request.duration_minutes is not None:
            entry.duration_minutes = request.duration_minutes
            # Recalculate amount if hourly rate exists
            if entry.hourly_rate and entry.is_billable:
                entry.amount = (request.duration_minutes / 60) * entry.hourly_rate
        
        if request.is_billable is not None:
            entry.is_billable = request.is_billable
            # Recalculate amount based on billable status
            if entry.hourly_rate:
                if request.is_billable:
                    entry.amount = (entry.duration_minutes / 60) * entry.hourly_rate
                else:
                    entry.amount = 0
        
        entry.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(entry)
        
        return {
            "id": entry.id,
            "duration_minutes": entry.duration_minutes,
            "description": entry.description,
            "is_billable": entry.is_billable,
            "amount": entry.amount,
            "updated_at": entry.updated_at.isoformat(),
            "message": "Time entry updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update entry error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update entry: {str(e)}")

@router.delete("/time/entries/{entry_id}")
async def delete_time_entry(
    entry_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a time entry"""
    try:
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            return {"message": "Entry deleted successfully (demo mode)", "demo_mode": True}
        
        entry = db.query(TimeEntry).filter(
            TimeEntry.id == entry_id,
            TimeEntry.user_id == current_user.id
        ).first()
        
        if not entry:
            raise HTTPException(404, "Time entry not found")
        
        if entry.is_billed:
            raise HTTPException(400, "Cannot delete billed time entry")
        
        db.delete(entry)
        db.commit()
        
        return {"message": "Time entry deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete entry error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete entry: {str(e)}")

# Enhanced reporting routes
@router.get("/reports/detailed")
async def get_detailed_report(
    days: int = Query(30, ge=1, le=365),
    board_id: Optional[str] = None,
    group_by: str = Query("day", regex="^(day|week|month|board|card)$"),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed time tracking report with grouping options"""
    try:
        # Demo mode handling
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            return {
                "period_days": days,
                "total_hours": 42.5,
                "total_minutes": 2550,
                "total_entries": 28,
                "total_amount": 850.0,
                "today_hours": 3.2,
                "week_hours": 18.7,
                "daily_average": 1.4,
                "board_breakdown": [
                    {"board_id": "demo_board_1", "total_minutes": 1200, "total_entries": 15, "total_amount": 400.0}
                ],
                "recent_entries": [
                    {"id": 1, "card_name": "Fix login issues", "duration_hours": 2.5, "created_at": datetime.now().isoformat()}
                ],
                "demo_mode": True
            }
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Base query
        query = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.created_at >= start_date,
            TimeEntry.end_time.isnot(None)  # Only completed entries
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
        card_stats = {}
        
        for entry in entries:
            # Board grouping
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
            
            # Card grouping
            if entry.card_id not in card_stats:
                card_stats[entry.card_id] = {
                    "card_id": entry.card_id,
                    "card_name": entry.card_name,
                    "total_minutes": 0,
                    "total_entries": 0,
                    "total_amount": 0
                }
            card_stats[entry.card_id]["total_minutes"] += entry.duration_minutes or 0
            card_stats[entry.card_id]["total_entries"] += 1
            card_stats[entry.card_id]["total_amount"] += entry.amount or 0
        
        # Time series data for charts
        time_series = []
        if group_by == "day":
            current_date = start_date.date()
            end_date_only = end_date.date()
            while current_date <= end_date_only:
                day_entries = [e for e in entries if e.created_at.date() == current_date]
                day_minutes = sum(entry.duration_minutes or 0 for entry in day_entries)
                time_series.append({
                    "date": current_date.isoformat(),
                    "hours": round(day_minutes / 60, 2),
                    "entries": len(day_entries),
                    "amount": sum(entry.amount or 0 for entry in day_entries)
                })
                current_date += timedelta(days=1)
        
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
            "card_breakdown": list(card_stats.values())[:10],  # Top 10 cards
            "time_series": time_series,
            "recent_entries": [
                {
                    "id": entry.id,
                    "card_name": entry.card_name,
                    "duration_hours": round((entry.duration_minutes or 0) / 60, 2),
                    "amount": entry.amount,
                    "created_at": entry.created_at.isoformat()
                }
                for entry in sorted(entries, key=lambda x: x.created_at, reverse=True)[:10]
            ]
        }
        
    except Exception as e:
        logger.error(f"Report error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")

@router.get("/reports/board/{board_id}")
async def get_board_report(
    board_id: str,
    days: int = Query(30, ge=1, le=365),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive report for specific board"""
    try:
        # Demo mode handling
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            return {
                "board_id": board_id,
                "period_days": days,
                "today_hours": 2.5,
                "week_hours": 12.3,
                "total_hours": 45.2,
                "total_entries": 23,
                "daily_average": 1.5,
                "top_cards": [
                    {"card_id": "demo_card_1", "card_name": "Login Bug", "total_hours": 5.2}
                ],
                "recent_entries": [],
                "demo_mode": True
            }
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        entries = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.board_id == board_id,
            TimeEntry.created_at >= start_date,
            TimeEntry.end_time.isnot(None)
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
        
        # Top cards by time
        card_totals = {}
        for entry in entries:
            if entry.card_id not in card_totals:
                card_totals[entry.card_id] = {
                    "card_id": entry.card_id,
                    "card_name": entry.card_name,
                    "total_minutes": 0,
                    "total_entries": 0
                }
            card_totals[entry.card_id]["total_minutes"] += entry.duration_minutes or 0
            card_totals[entry.card_id]["total_entries"] += 1
        
        top_cards = sorted(
            card_totals.values(),
            key=lambda x: x["total_minutes"],
            reverse=True
        )[:5]
        
        return {
            "board_id": board_id,
            "period_days": days,
            "today_hours": round(today_minutes / 60, 2),
            "week_hours": round(week_minutes / 60, 2),
            "total_hours": round(total_minutes / 60, 2),
            "total_entries": len(entries),
            "total_amount": sum(entry.amount or 0 for entry in entries),
            "daily_average": round((total_minutes / 60) / max(days, 1), 2),
            "top_cards": [
                {
                    "card_id": card["card_id"],
                    "card_name": card["card_name"],
                    "total_hours": round(card["total_minutes"] / 60, 2),
                    "total_entries": card["total_entries"]
                }
                for card in top_cards
            ],
            "recent_entries": [
                {
                    "id": entry.id,
                    "card_id": entry.card_id,
                    "card_name": entry.card_name,
                    "duration_minutes": entry.duration_minutes,
                    "amount": entry.amount,
                    "created_at": entry.created_at.isoformat()
                }
                for entry in sorted(entries, key=lambda x: x.created_at, reverse=True)[:10]
            ]
        }
        
    except Exception as e:
        logger.error(f"Board report error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate board report: {str(e)}")

# User management routes
@router.get("/user/profile")
async def get_user_profile(current_user = Depends(get_current_user)):
    """Get comprehensive user profile"""
    try:
        return {
            "id": getattr(current_user, 'id', 0),
            "email": getattr(current_user, 'email', 'demo@example.com'),
            "name": getattr(current_user, 'name', 'Demo User'),
            "trello_id": getattr(current_user, 'trello_id', 'demo_user'),
            "subscription_tier": getattr(current_user, 'subscription_tier', 'free'),
            "hourly_rate": getattr(current_user, 'hourly_rate', 50.0),
            "currency": getattr(current_user, 'currency', 'USD'),
            "created_at": getattr(current_user, 'created_at', datetime.utcnow()).isoformat(),
            "last_active": getattr(current_user, 'last_active', datetime.utcnow()).isoformat(),
            "demo_mode": hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__)
        }
    except Exception as e:
        logger.error(f"Get profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user profile")

@router.put("/user/profile")
async def update_user_profile(
    request: UserProfileUpdate,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user profile"""
    try:
        # Demo mode handling
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            return {
                "message": "Profile updated successfully (demo mode)",
                "demo_mode": True
            }
        
        # Update fields
        if request.name is not None:
            current_user.name = request.name
        if request.email is not None:
            current_user.email = request.email
        if request.hourly_rate is not None:
            current_user.hourly_rate = max(0, request.hourly_rate)
        if request.currency is not None:
            current_user.currency = request.currency
        
        db.commit()
        db.refresh(current_user)
        
        return {
            "message": "Profile updated successfully",
            "user": {
                "name": current_user.name,
                "email": current_user.email,
                "hourly_rate": current_user.hourly_rate,
                "currency": current_user.currency
            }
        }
        
    except Exception as e:
        logger.error(f"Update profile error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")

@router.get("/user/stats")
async def get_user_stats(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user statistics summary"""
    try:
        # Demo mode handling
        if db is None or hasattr(current_user, '__class__') and 'Demo' in str(current_user.__class__):
            return {
                "total_time_tracked": {"hours": 156.5, "entries": 89},
                "this_month": {"hours": 42.3, "entries": 28},
                "this_week": {"hours": 18.7, "entries": 12},
                "today": {"hours": 3.2, "entries": 2},
                "total_earned": 3130.0,
                "active_boards": 3,
                "demo_mode": True
            }
        
        now = datetime.utcnow()
        
        # All time stats
        all_entries = db.query(TimeEntry).filter(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.isnot(None)
        ).all()
        
        total_minutes = sum(entry.duration_minutes or 0 for entry in all_entries)
        total_earned = sum(entry.amount or 0 for entry in all_entries)
        
        # This month
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_entries = [e for e in all_entries if e.created_at >= month_start]
        month_minutes = sum(entry.duration_minutes or 0 for entry in month_entries)
        
        # This week
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_entries = [e for e in all_entries if e.created_at >= week_start]
        week_minutes = sum(entry.duration_minutes or 0 for entry in week_entries)
        
        # Today
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_entries = [e for e in all_entries if e.created_at >= today_start]
        today_minutes = sum(entry.duration_minutes or 0 for entry in today_entries)
        
        # Active boards count
        active_boards = len(set(entry.board_id for entry in all_entries if entry.board_id))
        
        return {
            "total_time_tracked": {
                "hours": round(total_minutes / 60, 1),
                "entries": len(all_entries)
            },
            "this_month": {
                "hours": round(month_minutes / 60, 1),
                "entries": len(month_entries)
            },
            "this_week": {
                "hours": round(week_minutes / 60, 1),
                "entries": len(week_entries)
            },
            "today": {
                "hours": round(today_minutes / 60, 1),
                "entries": len(today_entries)
            },
            "total_earned": round(total_earned, 2),
            "active_boards": active_boards
        }
        
    except Exception as e:
        logger.error(f"Get user stats error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user statistics")    