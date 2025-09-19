from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, Boolean, JSON, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from db import Base
import enum

class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"

class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    trello_id = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    avatar_url = Column(String)
    subscription_tier = Column(Enum(SubscriptionTier), default=SubscriptionTier.FREE)
    subscription_expires = Column(DateTime)
    
    # Billing settings
    hourly_rate = Column(Float, default=0.0)
    currency = Column(String, default="USD")
    company_name = Column(String)
    billing_address = Column(Text)
    tax_id = Column(String)
    
    # Usage tracking
    monthly_tracked_hours = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    time_entries = relationship("TimeEntry", back_populates="user")
    projects = relationship("Project", back_populates="user")
    clients = relationship("Client", back_populates="user")
    invoices = relationship("Invoice", back_populates="user")
    goals = relationship("Goal", back_populates="user")
    integrations = relationship("Integration", back_populates="user")

class Client(Base):
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, nullable=False)
    email = Column(String)
    company = Column(String)
    hourly_rate = Column(Float)
    address = Column(Text)
    phone = Column(String)
    notes = Column(Text)
    color = Column(String, default="#0079bf")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="clients")
    projects = relationship("Project", back_populates="client")
    invoices = relationship("Invoice", back_populates="client")

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    
    name = Column(String, nullable=False)
    description = Column(Text)
    trello_board_id = Column(String, index=True)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.ACTIVE)
    
    # Budget and rates
    budget_hours = Column(Float)
    budget_amount = Column(Float)
    hourly_rate = Column(Float)
    
    # Dates
    start_date = Column(DateTime)
    deadline = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Settings
    color = Column(String, default="#0079bf")
    is_billable = Column(Boolean, default=True)
    require_description = Column(Boolean, default=False)
    auto_track = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="projects")
    client = relationship("Client", back_populates="projects")
    time_entries = relationship("TimeEntry", back_populates="project")

class TimeEntry(Base):
    __tablename__ = "time_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    
    # Trello integration
    card_id = Column(String, index=True)
    card_name = Column(String)
    board_id = Column(String)
    list_name = Column(String)
    
    # Time tracking
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration_minutes = Column(Float)
    is_manual = Column(Boolean, default=False)
    
    # Details
    description = Column(Text)
    tags = Column(JSON)  # Array of strings
    hourly_rate = Column(Float)
    amount = Column(Float)
    
    # Status
    is_billable = Column(Boolean, default=True)
    is_billed = Column(Boolean, default=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="time_entries")
    project = relationship("Project", back_populates="time_entries")
    invoice = relationship("Invoice", back_populates="time_entries")

class Goal(Base):
    __tablename__ = "goals"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    title = Column(String, nullable=False)
    type = Column(String)  # daily, weekly, monthly, project
    target_hours = Column(Float)
    target_amount = Column(Float)
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="goals")

class Invoice(Base):
    __tablename__ = "invoices"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    client_id = Column(Integer, ForeignKey("clients.id"))
    
    # Invoice details
    invoice_number = Column(String, unique=True)
    title = Column(String)
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.DRAFT)
    
    # Amounts
    subtotal = Column(Float, default=0.0)
    tax_rate = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    
    # Dates
    issue_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime)
    paid_date = Column(DateTime)
    
    # Content
    notes = Column(Text)
    terms = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="invoices")
    client = relationship("Client", back_populates="invoices")
    time_entries = relationship("TimeEntry", back_populates="invoice")

class Integration(Base):
    __tablename__ = "integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    service = Column(String)  # slack, zapier, quickbooks, etc.
    is_active = Column(Boolean, default=True)
    settings = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="integrations")

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)  # timer_started, invoice_sent, etc.
    entity_type = Column(String)  # timeentry, invoice, etc.
    entity_id = Column(Integer)
    meta_data = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)

class Report(Base):
    __tablename__ = "reports"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    type = Column(String)  # time_summary, project_profitability, etc.
    filters = Column(JSON)
    schedule = Column(String)  # once, daily, weekly, monthly
    is_active = Column(Boolean, default=True)
    last_generated = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)