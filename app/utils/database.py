"""
Database configuration and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from decouple import config
import os

# Database URL from environment variables
DATABASE_URL = config(
    "DATABASE_URL", 
    # To be deleted or changed for production
    default="postgresql://inangara:pass@localhost:5433/prod_real_estate_db"
)

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False  # Set to True for SQL query logging
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

def get_db():
    """
    Dependency to get database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
