"""
Investor profile model for users with investor role
"""

from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.utils.database import Base


class InvestorProfile(Base):
    """Investor profile model"""
    __tablename__ = "investor_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Investment Information
    investment_experience = Column(String(50), nullable=True)  # beginner, intermediate, advanced, expert
    investment_focus = Column(JSON, nullable=True)  # Array: residential, commercial, industrial, land
    investment_strategy = Column(JSON, nullable=True)  # Array: buy_hold, fix_flip, wholesale, reits
    
    # Financial Capacity
    total_investment_capital = Column(Float, nullable=True)
    available_capital = Column(Float, nullable=True)
    annual_income = Column(Float, nullable=True)
    net_worth = Column(Float, nullable=True)
    credit_score = Column(Integer, nullable=True)
    
    # Portfolio Information
    total_properties_owned = Column(Integer, default=0)
    total_properties_managed = Column(Integer, default=0)
    portfolio_value = Column(Float, nullable=True)
    annual_roi = Column(Float, nullable=True)
    properties_owned = Column(JSON, nullable=True)  # Array of property IDs
    
    # Investment Preferences
    preferred_property_types = Column(JSON, nullable=True)  # Array of property types
    preferred_locations = Column(JSON, nullable=True)  # Array of locations/zip codes
    budget_range_min = Column(Float, nullable=True)
    budget_range_max = Column(Float, nullable=True)
    preferred_deal_size = Column(String(50), nullable=True)  # small, medium, large, mega
    
    # Risk Profile
    risk_tolerance = Column(String(50), nullable=True)  # conservative, moderate, aggressive
    investment_timeline = Column(String(50), nullable=True)  # short_term, medium_term, long_term
    liquidity_needs = Column(String(50), nullable=True)  # high, medium, low
    
    # Professional Information
    company_name = Column(String(200), nullable=True)
    job_title = Column(String(100), nullable=True)
    industry = Column(String(100), nullable=True)
    years_in_industry = Column(Integer, nullable=True)
    
    # Investment History
    first_investment_date = Column(DateTime(timezone=True), nullable=True)
    total_investments_made = Column(Integer, default=0)
    successful_deals = Column(Integer, default=0)
    failed_deals = Column(Integer, default=0)
    average_deal_size = Column(Float, nullable=True)
    
    # Network & Partnerships
    investment_partners = Column(JSON, nullable=True)  # Array of partner user IDs
    preferred_partnership_types = Column(JSON, nullable=True)  # Array of partnership types
    networking_events_attended = Column(Integer, default=0)
    
    # Goals & Objectives
    investment_goals = Column(Text, nullable=True)  # JSON object with goals
    target_roi = Column(Float, nullable=True)
    target_cash_flow = Column(Float, nullable=True)
    exit_strategy_preferences = Column(JSON, nullable=True)  # Array of exit strategies
    
    # Status & Verification
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    verification_date = Column(DateTime(timezone=True), nullable=True)
    accreditation_status = Column(String(50), nullable=True)  # accredited, non_accredited
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="investor_profile")

    def __repr__(self):
        return f"<InvestorProfile(user_id={self.user_id}, investment_experience='{self.investment_experience}')>"
