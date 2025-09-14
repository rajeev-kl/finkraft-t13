import os
import sqlite3

from decouple import config
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from db import models

DATABASE_URL = config("DATABASE_URL", default="sqlite:///./finkraft.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_db_schema():
    """Ensure the database has expected tables/columns for simple local migrations.

    This attempts to create missing tables via SQLAlchemy's metadata.create_all
    then applies a lightweight ALTER TABLE to add the `raw_response` column
    to `ai_suggestions` if it is missing (sqlite simple migration).
    """
    # create tables if they don't exist
    models.Base.metadata.create_all(bind=engine)

    # For sqlite, check if column exists and add it if missing
    try:
        db_path = None
        if DATABASE_URL.startswith("sqlite:///"):
            db_path = DATABASE_URL.replace("sqlite:///", "")
        if db_path and os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info('ai_suggestions')")
            cols = [r[1] for r in cur.fetchall()]
            if "raw_response" not in cols:
                cur.execute("ALTER TABLE ai_suggestions ADD COLUMN raw_response TEXT")
                conn.commit()
            cur.close()
            conn.close()
    except Exception:
        # best-effort migration only; failures are non-fatal for dev mode
        pass
