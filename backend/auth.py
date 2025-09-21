import os
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends, Header
from sqlalchemy.orm import Session
from typing import Optional
import jwt  # PyJWT
import logging

logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"

def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None):
    """Create JWT access token with optional custom expiration"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=30)
    
    to_encode = {
        "sub": user_id, 
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access_token"
    }
    
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Created access token for user: {user_id}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"Failed to create access token: {e}")
        raise HTTPException(500, "Failed to create access token")

def verify_token(token: str) -> str:
    """Verify JWT token and return user ID"""
    try:
        # Handle demo tokens
        if token.startswith("demo_token"):
            logger.info("Demo token detected")
            return "demo_user_" + token.split("_")[-1]
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        
        if user_id is None:
            raise HTTPException(401, "Invalid token: missing user ID")
        
        # Check token expiration
        exp = payload.get("exp")
        if exp and datetime.utcnow() > datetime.fromtimestamp(exp):
            raise HTTPException(401, "Token has expired")
        
        logger.debug(f"Token verified for user: {user_id}")
        return user_id
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(401, "Token has expired")
    except jwt.JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(401, "Invalid token")
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(401, "Token verification failed")

async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(None)  # Will be injected properly
):
    """Get current user from authorization header"""
    
    # Extract token from header
    if not authorization:
        raise HTTPException(401, "Authorization header missing")
    
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Invalid authorization header format")
    
    token = authorization.split(" ")[1]
    
    try:
        user_id = verify_token(token)
        
        # If database is not available, return demo user
        if db is None:
            logger.info("Database not available, returning demo user")
            return create_demo_user(user_id)
        
        # Import here to avoid circular imports
        from models import User
        
        # Get or create user
        user = db.query(User).filter(User.trello_id == user_id).first()
        
        if not user:
            logger.info(f"Creating new user for ID: {user_id}")
            user = User(
                trello_id=user_id,
                email=f"{user_id}@trello.local",
                name="Trello User"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            # Update last active time
            user.last_active = datetime.utcnow()
            db.commit()
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        raise HTTPException(500, "Failed to authenticate user")

def create_demo_user(user_id: str):
    """Create a demo user object when database is not available"""
    class DemoUser:
        def __init__(self, user_id):
            self.id = hash(user_id) % 1000000  # Generate consistent ID
            self.trello_id = user_id
            self.email = f"{user_id}@demo.local"
            self.name = "Demo User"
            self.subscription_tier = "free"
            self.hourly_rate = 50.0
            self.currency = "USD"
            self.created_at = datetime.utcnow()
            self.last_active = datetime.utcnow()
    
    return DemoUser(user_id)

async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(None)
):
    """Get current user if authenticated, otherwise return None"""
    try:
        return await get_current_user(authorization, db)
    except HTTPException:
        return None

def create_refresh_token(user_id: str) -> str:
    """Create a refresh token for long-term authentication"""
    expire = datetime.utcnow() + timedelta(days=90)
    to_encode = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh_token"
    }
    
    try:
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    except Exception as e:
        logger.error(f"Failed to create refresh token: {e}")
        raise HTTPException(500, "Failed to create refresh token")

def refresh_access_token(refresh_token: str) -> str:
    """Create new access token from refresh token"""
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        
        if payload.get("type") != "refresh_token":
            raise HTTPException(401, "Invalid refresh token")
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid refresh token")
        
        # Create new access token
        return create_access_token(user_id)
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Refresh token has expired")
    except jwt.JWTError:
        raise HTTPException(401, "Invalid refresh token")

def validate_api_key(api_key: str) -> bool:
    """Validate API key for external integrations"""
    # For demo purposes, accept any key that starts with "timezz_"
    if api_key.startswith("timezz_"):
        return True
    
    # In production, validate against database or environment variable
    valid_keys = os.getenv("VALID_API_KEYS", "").split(",")
    return api_key in valid_keys

async def get_api_user(api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Get user from API key for external integrations"""
    if not api_key:
        raise HTTPException(401, "API key required")
    
    if not validate_api_key(api_key):
        raise HTTPException(401, "Invalid API key")
    
    # Return a system user for API access
    return create_demo_user("api_user_" + api_key[-8:])

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.hash(password)
    except ImportError:
        logger.warning("Passlib not available, using simple hash (not secure!)")
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return pwd_context.verify(plain_password, hashed_password)
    except ImportError:
        logger.warning("Passlib not available, using simple comparison (not secure!)")
        import hashlib
        return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password