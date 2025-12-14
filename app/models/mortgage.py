"""
Mortgage Scenario Model

This module defines the database model for storing saved mortgage calculator scenarios.
Users can save their mortgage calculations for later reference.
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db import Base


class MortgageScenario(Base):
    """
    Model for storing saved mortgage calculator scenarios.
    
    Attributes:
        id: Primary key
        user_id: Foreign key to the user who created the scenario
        name: User-defined name for the scenario
        compare_mode: Whether this scenario includes comparison data
        scenario_data: JSON string containing all scenario parameters
        created_at: When the scenario was created
        updated_at: When the scenario was last updated
    """
    __tablename__ = "mortgage_scenarios"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    compare_mode = Column(Boolean, default=False)
    scenario_data = Column(Text, nullable=False)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to user
    user = relationship("User", backref="mortgage_scenarios")

