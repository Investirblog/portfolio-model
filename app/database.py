# ============================================================
# database.py — Connexion SQLAlchemy + session
# ============================================================
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,       # teste la connexion avant chaque requête
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dépendance FastAPI — fournit une session DB par requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
