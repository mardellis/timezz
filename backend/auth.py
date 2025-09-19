import os
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends, Header
from sqlalchemy.orm import Session
from typing import Optional
import jwt  # PyJWT
from models import User
from db import get_db

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ALGORITHM = "HS256"

def create_access_token(user_id: str):
    expire = datetime.utcnow() + timedelta(days=30)
    to_encode = {"sub": user_id, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(401, "Invalid token")
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")

async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header")
    
    token = authorization.split(" ")[1]
    user_id = verify_token(token)
    
    # Get or create user
    user = db.query(User).filter(User.trello_id == user_id).first()
    if not user:
        user = User(trello_id=user_id, email=f"{user_id}@trello.local")
        db.add(user)
        db.commit()
        db.refresh(user)
    
    return user