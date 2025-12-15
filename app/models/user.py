from sqlalchemy import Column, Integer, String, LargeBinary, DateTime, Boolean
from datetime import datetime
from app.models import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    profile_picture = Column(LargeBinary, nullable=True)  # Store image data
    profile_picture_type = Column(String, nullable=True)  # MIME type (image/jpeg, image/png, etc.)
    dark_mode = Column(Boolean, default=False)  # User preference for dark mode
    tutorial_completed = Column(Boolean, default=False)  # Track if user completed onboarding tutorial
    tutorial_step = Column(Integer, default=0)  # Current step in tutorial (0 = not started)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
