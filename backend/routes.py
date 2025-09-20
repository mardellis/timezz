from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from datetime import datetime, timedelta
from typing import Optional, List
import json

from db import get_db
from auth import get_current_user
from models import User, TimeEntry, Project, Client, Goal, Invoice

router = APIRouter()

# Auth Routes
@router.post("/auth/login")
async def login(
    login_data: dict,
    db: Session = Depends(get_db)
):
    from auth import create_access_token
    
    trello_id = login_data.get("trello_user_id")
    if not trello_id:
        raise HTTPException(400, "Missing trello_user_id")
    
    # Get or create user
    user = db.query(User).filter(User.trello_id == trello_id).first()
    if not user:
        user = User(
            trello_id=trello_id,
            email=login_data.get("email", f"{trello_id}@trello.local"),
            name=login_data.get("name", f"User {trello_id}")
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # Update last active
    user.last_active = datetime.utcnow()
    db.commit()
    
    token = create_access_token(trello_id)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "trello_id": user.trello_id
        }
    }

# Timer Routes
@router.get("/time/active")
async def get_active_timer(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check for running timer (no end_time)
    active_entry = db.query(TimeEntry).filter(
        and_(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.is_(None)
        )
    ).first()
    
    if active_entry:
        return {
            "active": True,
            "id": active_entry.id,
            "started_at": active_entry.start_time.isoformat(),
            "card_name": active_entry.card_name,
            "project_id": active_entry.project_id,
            "description": active_entry.description
        }
    
    return {"active": False}

@router.post("/time/start")
async def start_timer(
    timer_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Stop any existing timer
    existing = db.query(TimeEntry).filter(
        and_(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.is_(None)
        )
    ).first()
    
    if existing:
        existing.end_time = datetime.utcnow()
        existing.duration_minutes = (existing.end_time - existing.start_time).total_seconds() / 60
        if existing.project_id:
            project = db.query(Project).get(existing.project_id)
            if project and project.hourly_rate:
                existing.hourly_rate = project.hourly_rate
                existing.amount = existing.duration_minutes / 60 * project.hourly_rate
    
    # Create new timer entry
    new_entry = TimeEntry(
        user_id=current_user.id,
        project_id=timer_data.get("project_id"),
        card_id=timer_data.get("card_id"),
        card_name=timer_data.get("card_name", "Unnamed Task"),
        board_id=timer_data.get("board_id"),
        list_name=timer_data.get("list_name"),
        start_time=datetime.utcnow(),
        description=timer_data.get("description", ""),
        is_manual=False
    )
    
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    
    return {
        "id": new_entry.id,
        "started_at": new_entry.start_time.isoformat(),
        "card_name": new_entry.card_name,
        "project_id": new_entry.project_id
    }

@router.post("/time/stop")
async def stop_timer(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Find active timer
    active_entry = db.query(TimeEntry).filter(
        and_(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.is_(None)
        )
    ).first()
    
    if not active_entry:
        raise HTTPException(404, "No active timer found")
    
    # Stop the timer
    active_entry.end_time = datetime.utcnow()
    active_entry.duration_minutes = (active_entry.end_time - active_entry.start_time).total_seconds() / 60
    
    # Calculate amount if project has rate
    if active_entry.project_id:
        project = db.query(Project).get(active_entry.project_id)
        if project and project.hourly_rate:
            active_entry.hourly_rate = project.hourly_rate
            active_entry.amount = active_entry.duration_minutes / 60 * project.hourly_rate
    elif current_user.hourly_rate:
        active_entry.hourly_rate = current_user.hourly_rate
        active_entry.amount = active_entry.duration_minutes / 60 * current_user.hourly_rate
    
    db.commit()
    
    return {
        "id": active_entry.id,
        "duration_minutes": active_entry.duration_minutes,
        "amount": active_entry.amount or 0
    }

@router.get("/time/entries")
async def get_time_entries(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    project_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    query = db.query(TimeEntry).filter(TimeEntry.user_id == current_user.id)
    
    if project_id:
        query = query.filter(TimeEntry.project_id == project_id)
    
    if start_date:
        query = query.filter(TimeEntry.start_time >= datetime.fromisoformat(start_date))
    
    if end_date:
        query = query.filter(TimeEntry.start_time <= datetime.fromisoformat(end_date))
    
    entries = query.order_by(desc(TimeEntry.start_time)).offset(offset).limit(limit).all()
    
    result = []
    for entry in entries:
        result.append({
            "id": entry.id,
            "card_name": entry.card_name,
            "project_id": entry.project_id,
            "start_time": entry.start_time.isoformat() if entry.start_time else None,
            "end_time": entry.end_time.isoformat() if entry.end_time else None,
            "duration_minutes": entry.duration_minutes or 0,
            "amount": entry.amount or 0,
            "description": entry.description,
            "is_billable": entry.is_billable,
            "created_at": entry.created_at.isoformat()
        })
    
    return result

@router.post("/time/entries")
async def create_manual_entry(
    entry_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    start_time = datetime.fromisoformat(entry_data["start_time"])
    end_time = datetime.fromisoformat(entry_data["end_time"])
    
    if start_time >= end_time:
        raise HTTPException(400, "End time must be after start time")
    
    duration_minutes = (end_time - start_time).total_seconds() / 60
    
    # Calculate amount
    hourly_rate = entry_data.get("hourly_rate")
    if not hourly_rate and entry_data.get("project_id"):
        project = db.query(Project).get(entry_data["project_id"])
        if project:
            hourly_rate = project.hourly_rate
    if not hourly_rate:
        hourly_rate = current_user.hourly_rate or 0
    
    amount = duration_minutes / 60 * hourly_rate if hourly_rate else 0
    
    entry = TimeEntry(
        user_id=current_user.id,
        project_id=entry_data.get("project_id"),
        card_name=entry_data["card_name"],
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration_minutes,
        description=entry_data.get("description", ""),
        hourly_rate=hourly_rate,
        amount=amount,
        is_manual=True,
        is_billable=entry_data.get("is_billable", True)
    )
    
    db.add(entry)
    db.commit()
    db.refresh(entry)
    
    return {
        "id": entry.id,
        "duration_minutes": entry.duration_minutes,
        "amount": entry.amount
    }

# Project Routes
@router.get("/projects")
async def get_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    projects = db.query(Project).filter(Project.user_id == current_user.id).all()
    
    result = []
    for project in projects:
        # Get project stats
        total_time = db.query(func.sum(TimeEntry.duration_minutes)).filter(
            and_(
                TimeEntry.user_id == current_user.id,
                TimeEntry.project_id == project.id
            )
        ).scalar() or 0
        
        total_earnings = db.query(func.sum(TimeEntry.amount)).filter(
            and_(
                TimeEntry.user_id == current_user.id,
                TimeEntry.project_id == project.id
            )
        ).scalar() or 0
        
        result.append({
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "client_id": project.client_id,
            "status": project.status,
            "hourly_rate": project.hourly_rate,
            "color": project.color,
            "total_hours": total_time / 60,
            "total_earnings": total_earnings,
            "created_at": project.created_at.isoformat()
        })
    
    return result

@router.post("/projects")
async def create_project(
    project_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    project = Project(
        user_id=current_user.id,
        name=project_data["name"],
        description=project_data.get("description", ""),
        client_id=project_data.get("client_id"),
        hourly_rate=project_data.get("hourly_rate"),
        color=project_data.get("color", "#0079bf"),
        is_billable=project_data.get("is_billable", True)
    )
    
    db.add(project)
    db.commit()
    db.refresh(project)
    
    return {
        "id": project.id,
        "name": project.name,
        "client_id": project.client_id,
        "hourly_rate": project.hourly_rate
    }

# Client Routes
@router.get("/clients")
async def get_clients(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    clients = db.query(Client).filter(Client.user_id == current_user.id).all()
    
    result = []
    for client in clients:
        # Get client stats
        total_earnings = db.query(func.sum(TimeEntry.amount)).join(Project).filter(
            and_(
                Project.client_id == client.id,
                TimeEntry.user_id == current_user.id
            )
        ).scalar() or 0
        
        project_count = db.query(func.count(Project.id)).filter(
            Project.client_id == client.id
        ).scalar() or 0
        
        result.append({
            "id": client.id,
            "name": client.name,
            "email": client.email,
            "company": client.company,
            "hourly_rate": client.hourly_rate,
            "total_earnings": total_earnings,
            "project_count": project_count,
            "created_at": client.created_at.isoformat()
        })
    
    return result

@router.post("/clients")
async def create_client(
    client_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    client = Client(
        user_id=current_user.id,
        name=client_data["name"],
        email=client_data.get("email"),
        company=client_data.get("company"),
        hourly_rate=client_data.get("hourly_rate"),
        address=client_data.get("address"),
        phone=client_data.get("phone"),
        notes=client_data.get("notes")
    )
    
    db.add(client)
    db.commit()
    db.refresh(client)
    
    return {
        "id": client.id,
        "name": client.name,
        "email": client.email,
        "hourly_rate": client.hourly_rate
    }

# Reports Routes
@router.get("/reports/dashboard")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    
    # Today's stats
    today_entries = db.query(TimeEntry).filter(
        and_(
            TimeEntry.user_id == current_user.id,
            TimeEntry.start_time >= today_start
        )
    ).all()
    
    # Week's stats
    week_entries = db.query(TimeEntry).filter(
        and_(
            TimeEntry.user_id == current_user.id,
            TimeEntry.start_time >= week_start
        )
    ).all()
    
    # Active timer check
    active_timer = db.query(TimeEntry).filter(
        and_(
            TimeEntry.user_id == current_user.id,
            TimeEntry.end_time.is_(None)
        )
    ).first()
    
    today_hours = sum(entry.duration_minutes or 0 for entry in today_entries) / 60
    week_hours = sum(entry.duration_minutes or 0 for entry in week_entries) / 60
    week_earnings = sum(entry.amount or 0 for entry in week_entries)
    
    return {
        "total_hours": today_hours,
        "week_hours": week_hours,
        "week_earnings": week_earnings,
        "active_tasks": 1 if active_timer else 0,
        "recent_entries": len(today_entries)
    }

@router.get("/reports/detailed")
async def get_detailed_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=365)
):
    start_date = datetime.utcnow() - timedelta(days=days)
    
    entries = db.query(TimeEntry).filter(
        and_(
            TimeEntry.user_id == current_user.id,
            TimeEntry.start_time >= start_date,
            TimeEntry.end_time.isnot(None)
        )
    ).all()
    
    total_hours = sum(entry.duration_minutes or 0 for entry in entries) / 60
    total_earnings = sum(entry.amount or 0 for entry in entries)
    billable_hours = sum(entry.duration_minutes or 0 for entry in entries if entry.is_billable) / 60
    
    return {
        "total_hours": total_hours,
        "total_earnings": total_earnings,
        "billable_hours": billable_hours,
        "total_entries": len(entries),
        "average_session": total_hours / len(entries) if entries else 0,
        "productivity": (billable_hours / total_hours * 100) if total_hours > 0 else 0
    }