import os
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if not DATABASE_URL:
    if ENVIRONMENT == "production":
        raise RuntimeError(
            "DATABASE_URL is not set, but ENVIRONMENT=production. "
            "Refusing to silently fall back to a local SQLite file -- that file "
            "resets on every deploy and would silently wipe everyone's saved "
            "preferences. Set DATABASE_URL (a real Postgres connection string) "
            "and restart."
        )
    print("[database] No DATABASE_URL set -- using a local SQLite file. "
          "This is fine for development, but NOT for production.")
    DATABASE_URL = "sqlite:///./local_dev.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    cuisine = Column(String, nullable=True)
    budget = Column(String, nullable=True)       # e.g. "low", "medium", "high"
    min_rating = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    """Creates the table if it doesn't exist yet. Call this once on startup."""
    Base.metadata.create_all(bind=engine)


def save_preference(user_id: str, cuisine: str, budget: str, min_rating: float):
    """Save a new preference record after every successful query."""
    session = SessionLocal()
    try:
        pref = UserPreference(user_id=user_id, cuisine=cuisine, budget=budget, min_rating=min_rating)
        session.add(pref)
        session.commit()
    finally:
        session.close()


def get_recent_preferences(user_id: str, limit: int = 5):
    session = SessionLocal()
    try:
        rows = (
            session.query(UserPreference)
            .filter(UserPreference.user_id == user_id)
            .order_by(UserPreference.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"cuisine": r.cuisine, "budget": r.budget, "min_rating": r.min_rating}
            for r in rows
        ]
    finally:
        session.close()