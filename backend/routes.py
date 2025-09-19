from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_, desc, extract
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from db import get_db
from models import *
from auth import get_current_user, create_access_token
import uuid
from decimal import Decimal

router = APIRouter()

# ============= PYDANTIC SCHEMAS =============

class ClientCreate(BaseModel):
    name: str
    email: Optional[str] = None
    company: Optional[str] = None
    hourly_rate: Optional[float] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    color: str = "#0079bf"

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    client_id: Optional[int] = None
    trello_board_id: Optional[str] = None
    budget_hours: Optional[float] = None
    budget_amount: Optional[float] = None
    hourly_rate: Optional[float] = None
    start_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    is_billable: bool = True
    require_description: bool = False
    color: str = "#0079bf"

class TimeEntryCreate(BaseModel):
    card_id: str
    card_name: str
    board_id: str
    list_name: Optional[str] = None
    project_id: Optional[int] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = []
    is_billable: bool = True

class ManualTimeEntry(BaseModel):
    project_id: Optional[int] = None
    card_id: Optional[str] = None
    card_name: str
    description: str
    start_time: datetime
    end_time: datetime
    tags: Optional[List[str]] = []
    is_billable: bool = True

class GoalCreate(BaseModel):
    title: str
    type: str = "weekly"  # daily, weekly, monthly, project
    target_hours: Optional[float] = None
    target_amount: Optional[float] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None

class InvoiceCreate(BaseModel):
    client_id: int
    title: str
    time_entry_ids: List[int] = []
    due_days: int = 30
    tax_rate: float = 0.0
    discount: float = 0.0
    notes: Optional[str] = None
    terms: Optional[str] = None

# ============= AUTHENTICATION =============

class LoginRequest(BaseModel):
    trello_user_id: str
    trello_token: str
    name: Optional[str] = None
    email: Optional[str] = None

@router.post("/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    try:
        # Verify with Trello API in production
        user = db.query(User).filter(User.trello_id == request.trello_user_id).first()
        
        if not user:
            user = User(
                trello_id=request.trello_user_id,
                name=request.name or "Trello User",
                email=request.email or f"{request.trello_user_id}@trello.local",
                hourly_rate=75.0,  # Default rate
                subscription_tier=SubscriptionTier.FREE
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user.last_active = datetime.utcnow()
            db.commit()
        
        access_token = create_access_token(request.trello_user_id)
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "subscription_tier": user.subscription_tier,
                "hourly_rate": user.hourly_rate
            }
        }
    
    except Exception as e:
        raise HTTPException(500, f"Login failed: {str(e)}")

# ============= PREMIUM TIME TRACKING =============

@router.post("/time/start")
def start_timer(
    entry: TimeEntryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Stop any running timers
    active = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.end_time.is_(None)
    ).first()
    
    if active:
        active.end_time = datetime.utcnow()
        active.duration_minutes = (active.end_time - active.start_time).total_seconds() / 60
        active.amount = (active.duration_minutes / 60) * (active.hourly_rate or current_user.hourly_rate)
    
    # Get project and rate
    project = None
    hourly_rate = current_user.hourly_rate
    
    if entry.project_id:
        project = db.query(Project).filter(
            Project.id == entry.project_id,
            Project.user_id == current_user.id
        ).first()
        if project and project.hourly_rate:
            hourly_rate = project.hourly_rate
        elif project and project.client and project.client.hourly_rate:
            hourly_rate = project.client.hourly_rate
    
    new_entry = TimeEntry(
        user_id=current_user.id,
        project_id=entry.project_id,
        card_id=entry.card_id,
        card_name=entry.card_name,
        board_id=entry.board_id,
        list_name=entry.list_name,
        description=entry.description,
        tags=entry.tags,
        start_time=datetime.utcnow(),
        hourly_rate=hourly_rate,
        is_billable=entry.is_billable and (not project or project.is_billable)
    )
    
    db.add(new_entry)
    db.commit()
    
    return {
        "id": new_entry.id,
        "started_at": new_entry.start_time,
        "hourly_rate": hourly_rate,
        "project_name": project.name if project else None
    }

@router.post("/time/manual")
def create_manual_entry(
    entry: ManualTimeEntry,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Calculate duration and amount
    duration = (entry.end_time - entry.start_time).total_seconds() / 60
    
    if duration <= 0:
        raise HTTPException(400, "End time must be after start time")
    
    # Get rate
    project = None
    hourly_rate = current_user.hourly_rate
    
    if entry.project_id:
        project = db.query(Project).filter(
            Project.id == entry.project_id,
            Project.user_id == current_user.id
        ).first()
        if project and project.hourly_rate:
            hourly_rate = project.hourly_rate
    
    amount = (duration / 60) * hourly_rate
    
    new_entry = TimeEntry(
        user_id=current_user.id,
        project_id=entry.project_id,
        card_id=entry.card_id,
        card_name=entry.card_name,
        description=entry.description,
        start_time=entry.start_time,
        end_time=entry.end_time,
        duration_minutes=duration,
        hourly_rate=hourly_rate,
        amount=amount,
        tags=entry.tags,
        is_billable=entry.is_billable,
        is_manual=True
    )
    
    db.add(new_entry)
    db.commit()
    
    return {"id": new_entry.id, "duration_minutes": duration, "amount": amount}

# ============= CLIENT MANAGEMENT =============

@router.post("/clients")
def create_client(
    client: ClientCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_client = Client(
        user_id=current_user.id,
        **client.model_dump()
    )
    db.add(new_client)
    db.commit()
    db.refresh(new_client)
    return new_client

@router.get("/clients")
def get_clients(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    clients = db.query(Client).filter(
        Client.user_id == current_user.id,
        Client.is_active == True
    ).all()
    
    # Add project counts and revenue
    for client in clients:
        client.project_count = len(client.projects)
        client.total_revenue = sum(
            entry.amount or 0 for project in client.projects 
            for entry in project.time_entries if entry.amount
        )
    
    return clients

# ============= PROJECT MANAGEMENT =============

@router.post("/projects")
def create_project(
    project: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_project = Project(
        user_id=current_user.id,
        **project.model_dump()
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project

@router.get("/projects")
def get_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    projects = db.query(Project).options(
        joinedload(Project.client)
    ).filter(
        Project.user_id == current_user.id
    ).all()
    
    # Add statistics
    for project in projects:
        entries = project.time_entries
        project.total_hours = sum(e.duration_minutes or 0 for e in entries) / 60
        project.total_revenue = sum(e.amount or 0 for e in entries)
        project.progress = min(100, (project.total_hours / project.budget_hours * 100)) if project.budget_hours else 0
    
    return projects

# ============= ADVANCED REPORTING =============

@router.get("/reports/dashboard")
def get_dashboard(
    current_user: User = Depends(get_current_user),
    period: str = Query("week", description="today, week, month, year"),
    db: Session = Depends(get_db)
):
    now = datetime.utcnow()
    
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Get time entries for period
    entries = db.query(TimeEntry).options(
        joinedload(TimeEntry.project).joinedload(Project.client)
    ).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.start_time >= start,
        TimeEntry.end_time.isnot(None)
    ).all()
    
    total_hours = sum(e.duration_minutes or 0 for e in entries) / 60
    total_revenue = sum(e.amount or 0 for e in entries)
    billable_hours = sum(e.duration_minutes or 0 for e in entries if e.is_billable) / 60
    
    # Top projects
    project_stats = {}
    for entry in entries:
        if entry.project:
            proj_id = entry.project.id
            if proj_id not in project_stats:
                project_stats[proj_id] = {
                    "name": entry.project.name,
                    "client": entry.project.client.name if entry.project.client else None,
                    "hours": 0,
                    "revenue": 0
                }
            project_stats[proj_id]["hours"] += (entry.duration_minutes or 0) / 60
            project_stats[proj_id]["revenue"] += entry.amount or 0
    
    # Daily breakdown for charts
    daily_data = {}
    for entry in entries:
        day = entry.start_time.date().isoformat()
        if day not in daily_data:
            daily_data[day] = {"hours": 0, "revenue": 0}
        daily_data[day]["hours"] += (entry.duration_minutes or 0) / 60
        daily_data[day]["revenue"] += entry.amount or 0
    
    return {
        "period": period,
        "total_hours": round(total_hours, 2),
        "billable_hours": round(billable_hours, 2),
        "total_revenue": round(total_revenue, 2),
        "average_hourly_rate": round(total_revenue / total_hours, 2) if total_hours > 0 else 0,
        "projects": sorted(project_stats.values(), key=lambda x: x["hours"], reverse=True)[:5],
        "daily_breakdown": daily_data,
        "entries_count": len(entries)
    }

@router.get("/reports/productivity")
def get_productivity_report(
    current_user: User = Depends(get_current_user),
    days: int = Query(30, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.start_time >= start_date,
        TimeEntry.end_time.isnot(None)
    ).all()
    
    # Productivity metrics
    total_days = days
    days_worked = len(set(e.start_time.date() for e in entries))
    total_hours = sum(e.duration_minutes or 0 for e in entries) / 60
    
    # Peak hours analysis
    hour_distribution = {}
    for entry in entries:
        hour = entry.start_time.hour
        hour_distribution[hour] = hour_distribution.get(hour, 0) + (entry.duration_minutes or 0) / 60
    
    peak_hour = max(hour_distribution, key=hour_distribution.get) if hour_distribution else 9
    
    # Weekly pattern
    weekday_hours = [0] * 7  # Monday = 0
    for entry in entries:
        weekday = entry.start_time.weekday()
        weekday_hours[weekday] += (entry.duration_minutes or 0) / 60
    
    return {
        "period_days": days,
        "days_worked": days_worked,
        "work_frequency": round(days_worked / total_days * 100, 1),
        "total_hours": round(total_hours, 2),
        "average_hours_per_day": round(total_hours / days_worked, 2) if days_worked > 0 else 0,
        "peak_hour": peak_hour,
        "hour_distribution": hour_distribution,
        "weekday_hours": weekday_hours,
        "most_productive_day": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday_hours.index(max(weekday_hours))] if weekday_hours else "Monday"
    }

# ============= GOAL TRACKING =============

@router.post("/goals")
def create_goal(
    goal: GoalCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    new_goal = Goal(
        user_id=current_user.id,
        **goal.model_dump()
    )
    db.add(new_goal)
    db.commit()
    db.refresh(new_goal)
    return new_goal

@router.get("/goals/progress")
def get_goals_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    goals = db.query(Goal).filter(
        Goal.user_id == current_user.id,
        Goal.is_active == True
    ).all()
    
    results = []
    for goal in goals:
        # Calculate current progress
        if goal.period_start and goal.period_end:
            entries = db.query(TimeEntry).filter(
                TimeEntry.user_id == current_user.id,
                TimeEntry.start_time >= goal.period_start,
                TimeEntry.start_time <= goal.period_end,
                TimeEntry.end_time.isnot(None)
            ).all()
        else:
            entries = []
        
        current_hours = sum(e.duration_minutes or 0 for e in entries) / 60
        current_amount = sum(e.amount or 0 for e in entries)
        
        progress_percent = 0
        if goal.target_hours:
            progress_percent = min(100, (current_hours / goal.target_hours) * 100)
        elif goal.target_amount:
            progress_percent = min(100, (current_amount / goal.target_amount) * 100)
        
        results.append({
            "id": goal.id,
            "title": goal.title,
            "type": goal.type,
            "target_hours": goal.target_hours,
            "target_amount": goal.target_amount,
            "current_hours": round(current_hours, 2),
            "current_amount": round(current_amount, 2),
            "progress_percent": round(progress_percent, 1),
            "period_start": goal.period_start,
            "period_end": goal.period_end
        })
    
    return results

# ============= INVOICING =============

@router.post("/invoices")
def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get client
    client = db.query(Client).filter(
        Client.id == invoice_data.client_id,
        Client.user_id == current_user.id
    ).first()
    
    if not client:
        raise HTTPException(404, "Client not found")
    
    # Get time entries
    entries = db.query(TimeEntry).filter(
        TimeEntry.id.in_(invoice_data.time_entry_ids),
        TimeEntry.user_id == current_user.id,
        TimeEntry.is_billable == True,
        TimeEntry.is_billed == False
    ).all()
    
    if not entries:
        raise HTTPException(400, "No billable time entries found")
    
    # Calculate amounts
    subtotal = sum(e.amount or 0 for e in entries)
    tax_amount = subtotal * (invoice_data.tax_rate / 100)
    total = subtotal + tax_amount - invoice_data.discount
    
    # Generate invoice number
    invoice_number = f"INV-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
    
    # Create invoice
    invoice = Invoice(
        user_id=current_user.id,
        client_id=client.id,
        invoice_number=invoice_number,
        title=invoice_data.title,
        subtotal=subtotal,
        tax_rate=invoice_data.tax_rate,
        tax_amount=tax_amount,
        discount=invoice_data.discount,
        total_amount=total,
        due_date=datetime.utcnow() + timedelta(days=invoice_data.due_days),
        notes=invoice_data.notes,
        terms=invoice_data.terms
    )
    
    db.add(invoice)
    db.flush()
    
    # Mark entries as billed
    for entry in entries:
        entry.is_billed = True
        entry.invoice_id = invoice.id
    
    db.commit()
    db.refresh(invoice)
    
    return {
        "id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "total_amount": total,
        "entries_count": len(entries)
    }

@router.get("/invoices")
def get_invoices(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Invoice).options(
        joinedload(Invoice.client)
    ).filter(Invoice.user_id == current_user.id)
    
    if status:
        query = query.filter(Invoice.status == status)
    
    invoices = query.order_by(desc(Invoice.created_at)).all()
    
    # Add summary stats
    total_amount = sum(inv.total_amount for inv in invoices)
    paid_amount = sum(inv.total_amount for inv in invoices if inv.status == InvoiceStatus.PAID)
    
    return {
        "invoices": invoices,
        "summary": {
            "total_invoices": len(invoices),
            "total_amount": total_amount,
            "paid_amount": paid_amount,
            "outstanding": total_amount - paid_amount
        }
    }

# ============= TEAM COLLABORATION =============

@router.get("/time/team-summary")
def get_team_summary(
    current_user: User = Depends(get_current_user),
    board_id: str = Query(..., description="Trello board ID"),
    days: int = Query(7, description="Number of days"),
    db: Session = Depends(get_db)
):
    """Get team time tracking summary for a Trello board"""
    
    if current_user.subscription_tier == SubscriptionTier.FREE:
        raise HTTPException(403, "Team features require Pro or Enterprise subscription")
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get all entries for this board from all users (in production, filter by team)
    entries = db.query(TimeEntry).options(
        joinedload(TimeEntry.user)
    ).filter(
        TimeEntry.board_id == board_id,
        TimeEntry.start_time >= start_date,
        TimeEntry.end_time.isnot(None)
    ).all()
    
    # Group by user
    user_stats = {}
    card_stats = {}
    
    for entry in entries:
        user_id = entry.user.id
        if user_id not in user_stats:
            user_stats[user_id] = {
                "name": entry.user.name,
                "hours": 0,
                "cards_worked": set(),
                "revenue": 0
            }
        
        user_stats[user_id]["hours"] += (entry.duration_minutes or 0) / 60
        user_stats[user_id]["cards_worked"].add(entry.card_id)
        user_stats[user_id]["revenue"] += entry.amount or 0
        
        # Card stats
        if entry.card_id not in card_stats:
            card_stats[entry.card_id] = {
                "name": entry.card_name,
                "total_hours": 0,
                "contributors": set(),
                "status": entry.list_name
            }
        
        card_stats[entry.card_id]["total_hours"] += (entry.duration_minutes or 0) / 60
        card_stats[entry.card_id]["contributors"].add(entry.user.name)
    
    # Convert sets to counts
    for stats in user_stats.values():
        stats["cards_worked"] = len(stats["cards_worked"])
    
    for stats in card_stats.values():
        stats["contributors"] = list(stats["contributors"])
    
    return {
        "board_id": board_id,
        "period_days": days,
        "user_summary": user_stats,
        "card_summary": card_stats,
        "total_team_hours": sum(stats["hours"] for stats in user_stats.values()),
        "active_contributors": len(user_stats)
    }

# ============= INTEGRATIONS =============

@router.post("/integrations/slack")
def setup_slack_integration(
    webhook_url: str,
    channels: List[str],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.subscription_tier == SubscriptionTier.FREE:
        raise HTTPException(403, "Integrations require Pro or Enterprise subscription")
    
    integration = db.query(Integration).filter(
        Integration.user_id == current_user.id,
        Integration.service == "slack"
    ).first()
    
    if integration:
        integration.settings = {
            "webhook_url": webhook_url,
            "channels": channels,
            "notify_timer_start": True,
            "notify_daily_summary": True
        }
        integration.is_active = True
    else:
        integration = Integration(
            user_id=current_user.id,
            service="slack",
            settings={
                "webhook_url": webhook_url,
                "channels": channels,
                "notify_timer_start": True,
                "notify_daily_summary": True
            }
        )
        db.add(integration)
    
    db.commit()
    return {"message": "Slack integration configured successfully"}

# ============= AI INSIGHTS (Enterprise Feature) =============

@router.get("/insights/ai-recommendations")
def get_ai_insights(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.subscription_tier != SubscriptionTier.ENTERPRISE:
        raise HTTPException(403, "AI Insights require Enterprise subscription")
    
    # Get recent data for analysis
    recent_entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.start_time >= datetime.utcnow() - timedelta(days=30),
        TimeEntry.end_time.isnot(None)
    ).all()
    
    if not recent_entries:
        return {"insights": [], "message": "Not enough data for insights"}
    
    insights = []
    
    # Productivity pattern analysis
    hour_productivity = {}
    for entry in recent_entries:
        hour = entry.start_time.hour
        duration = entry.duration_minutes or 0
        if hour not in hour_productivity:
            hour_productivity[hour] = []
        hour_productivity[hour].append(duration)
    
    # Find peak productivity hours
    avg_productivity = {}
    for hour, durations in hour_productivity.items():
        avg_productivity[hour] = sum(durations) / len(durations)
    
    if avg_productivity:
        peak_hour = max(avg_productivity, key=avg_productivity.get)
        insights.append({
            "type": "productivity_peak",
            "title": "Optimal Work Hours",
            "message": f"You're most productive at {peak_hour}:00. Consider scheduling important tasks during this time.",
            "priority": "medium",
            "data": {"peak_hour": peak_hour, "avg_duration": round(avg_productivity[peak_hour], 1)}
        })
    
    # Project profitability analysis
    project_revenue = {}
    project_hours = {}
    
    for entry in recent_entries:
        if entry.project_id and entry.amount:
            proj_id = entry.project_id
            project_revenue[proj_id] = project_revenue.get(proj_id, 0) + entry.amount
            project_hours[proj_id] = project_hours.get(proj_id, 0) + (entry.duration_minutes or 0) / 60
    
    if project_revenue:
        profitability = {proj: rev / project_hours.get(proj, 1) for proj, rev in project_revenue.items()}
        
        if len(profitability) > 1:
            best_project = max(profitability, key=profitability.get)
            worst_project = min(profitability, key=profitability.get)
            
            best_rate = profitability[best_project]
            worst_rate = profitability[worst_project]
            
            if best_rate > worst_rate * 1.5:  # Significant difference
                insights.append({
                    "type": "profitability_gap",
                    "title": "Project Profitability Gap",
                    "message": f"Consider focusing more time on high-value projects. Rate difference: ${best_rate:.0f}/hr vs ${worst_rate:.0f}/hr",
                    "priority": "high",
                    "data": {"best_rate": best_rate, "worst_rate": worst_rate}
                })
    
    # Time tracking consistency
    daily_hours = {}
    for entry in recent_entries:
        day = entry.start_time.date()
        daily_hours[day] = daily_hours.get(day, 0) + (entry.duration_minutes or 0) / 60
    
    if len(daily_hours) >= 7:  # At least a week of data
        hours_values = list(daily_hours.values())
        avg_hours = sum(hours_values) / len(hours_values)
        consistency_score = 1 - (max(hours_values) - min(hours_values)) / avg_hours if avg_hours > 0 else 0
        
        if consistency_score < 0.7:  # Inconsistent tracking
            insights.append({
                "type": "consistency",
                "title": "Inconsistent Time Tracking",
                "message": f"Your daily hours vary significantly (avg: {avg_hours:.1f}h). Consider setting daily time goals.",
                "priority": "medium",
                "data": {"consistency_score": round(consistency_score * 100, 1), "avg_hours": round(avg_hours, 1)}
            })
    
    return {
        "insights": insights,
        "analysis_period": "30 days",
        "entries_analyzed": len(recent_entries)
    }

# ============= SUBSCRIPTION MANAGEMENT =============

@router.get("/subscription/usage")
def get_subscription_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Calculate current month usage
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    monthly_entries = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.created_at >= month_start,
        TimeEntry.end_time.isnot(None)
    ).count()
    
    monthly_hours = db.query(func.sum(TimeEntry.duration_minutes)).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.created_at >= month_start,
        TimeEntry.end_time.isnot(None)
    ).scalar() or 0
    
    monthly_hours = monthly_hours / 60
    
    # Define limits based on subscription
    limits = {
        SubscriptionTier.FREE: {"entries": 50, "hours": 40, "projects": 3, "clients": 2},
        SubscriptionTier.PRO: {"entries": 1000, "hours": 200, "projects": 50, "clients": 25},
        SubscriptionTier.ENTERPRISE: {"entries": -1, "hours": -1, "projects": -1, "clients": -1}  # Unlimited
    }
    
    current_limits = limits[current_user.subscription_tier]
    
    total_projects = db.query(Project).filter(Project.user_id == current_user.id).count()
    total_clients = db.query(Client).filter(Client.user_id == current_user.id).count()
    
    return {
        "subscription_tier": current_user.subscription_tier,
        "current_usage": {
            "monthly_entries": monthly_entries,
            "monthly_hours": round(monthly_hours, 2),
            "total_projects": total_projects,
            "total_clients": total_clients
        },
        "limits": current_limits,
        "usage_percentage": {
            "entries": round((monthly_entries / current_limits["entries"]) * 100, 1) if current_limits["entries"] > 0 else 0,
            "hours": round((monthly_hours / current_limits["hours"]) * 100, 1) if current_limits["hours"] > 0 else 0,
            "projects": round((total_projects / current_limits["projects"]) * 100, 1) if current_limits["projects"] > 0 else 0,
            "clients": round((total_clients / current_limits["clients"]) * 100, 1) if current_limits["clients"] > 0 else 0
        }
    }