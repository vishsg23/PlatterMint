"""
database.py
------------
Everything related to PostgreSQL lives here.

We store two things:
1. user_preferences -- each user's past queries (cuisine, budget, min rating).
   This is what the "Preference RAG" agent reads from, so returning users
   don't have to repeat themselves.
2. user_accounts -- an OPTIONAL, lightweight way to protect a name with a
   PIN (see check_user_pin below). This is NOT a real login system.

We are NOT storing restaurant data here --- restaurants always come live
from the Google Maps API, so that data is never stale.
"""

import os
import hashlib
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

# FIX (#9): previously this silently fell back to a local SQLite file any
# time DATABASE_URL was missing -- including in production, where that file
# lives on the container's disk and gets wiped on every redeploy. That means
# everyone's saved preferences could vanish with zero warning.
#
# Now: if ENVIRONMENT=production and DATABASE_URL is missing, we refuse to
# start instead of quietly losing data. Local development (the default)
# still "just works" with SQLite, same as before.
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
    """One row = one past query a user made, so we can look at their history."""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    cuisine = Column(String, nullable=True)
    budget = Column(String, nullable=True)       # e.g. "low", "medium", "high"
    min_rating = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserAccount(Base):
    """
    FIX (#8): optional, lightweight protection for a saved name.

    Before this, `user_id` was just a free-text box -- anyone could type
    "Vaishnavi" and read/influence Vaishnavi's saved preferences. This is
    NOT a real login system (no password reset, no email, no encryption
    beyond a hash) -- it's just enough to stop someone from casually using
    a name that isn't theirs.

    How it works, in plain terms:
    - If a name has never set a PIN, it stays "open" (works exactly like
      before -- anyone can use it, same as the old behavior).
    - The FIRST time someone sets a PIN for a name, that name becomes
      "claimed" -- from then on, using that name requires that same PIN.
    """
    __tablename__ = "user_accounts"

    user_id = Column(String, primary_key=True)
    pin_hash = Column(String, nullable=True)  # None = name is still "open" / unprotected


def init_db():
    """Creates both tables if they don't exist yet. Call this once on startup."""
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
    """
    Return the user's last few preference records, most recent first.
    This is our simple version of 'RAG' -- instead of a vector DB, we
    just retrieve structured history for this specific user.
    """
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


def _hash_pin(user_id: str, pin: str) -> str:
    """Turns a name+PIN into a one-way hash. We never store the raw PIN."""
    return hashlib.sha256(f"{user_id}:{pin}".encode("utf-8")).hexdigest()


def check_user_pin(user_id: str, pin: str | None):
    """
    Checks whether it's okay to use this name, given the (optional) PIN.
    Returns a tuple: (ok: bool, message: str)

    Plain-English rules:
    - Brand new name, no PIN given      -> OK, name stays open (old behavior)
    - Brand new name, PIN given         -> OK, and this name is now protected
    - Existing name, never had a PIN    -> OK, still open to anyone
    - Existing name, PIN set, matches   -> OK
    - Existing name, PIN set, wrong/missing -> NOT OK
    """
    session = SessionLocal()
    try:
        account = session.query(UserAccount).filter(UserAccount.user_id == user_id).first()

        if account is None:
            # first time we've ever seen this name
            if pin:
                session.add(UserAccount(user_id=user_id, pin_hash=_hash_pin(user_id, pin)))
                session.commit()
            return True, "ok"

        if account.pin_hash is None:
            # this name was never protected -- keep old, open behavior
            return True, "ok"

        if pin and _hash_pin(user_id, pin) == account.pin_hash:
            return True, "ok"

        return False, "This name is protected with a PIN. Enter the correct PIN, or pick a different name."
    finally:
        session.close()