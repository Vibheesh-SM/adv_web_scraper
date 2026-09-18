import os
import datetime
from sqlalchemy import create_engine, Column, String, Float, DateTime, Boolean, JSON, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Build database URL dynamically. Default to a local SQLite database for zero-config running.
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

if POSTGRES_USER and POSTGRES_PASSWORD and POSTGRES_DB:
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
else:
    # Use SQLite for 100% free / local zero-setup
    print("[Database] Using local SQLite database (threat_intel.db) for zero-setup execution.")
    DATABASE_URL = "sqlite:///threat_intel.db"
    # Set connect timeout to 30 seconds to allow concurrent access between Streamlit and Celery worker
    engine = create_engine(DATABASE_URL, connect_args={"timeout": 30})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class DBPost(Base):
    __tablename__ = "posts"

    # SQLite compatible layout (will run on pgvector too if needed, mapping vector to standard types)
    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(String, unique=True, index=True, nullable=False)
    platform = Column(String, index=True, nullable=False)
    text = Column(String, nullable=False)
    author_id = Column(String, nullable=False)
    author_name = Column(String, nullable=False)
    published_at = Column(DateTime, index=True, nullable=False)
    url = Column(String, nullable=False)
    
    # Analysis Fields
    threat_score = Column(Float, index=True, default=0.0)
    threat_label = Column(String, index=True)
    sentiment_score = Column(Float, default=0.0)
    flagged = Column(Boolean, index=True, default=False)
    processed_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Store engagement metrics as json/string depending on database target
    engagement = Column(JSON, default=dict)

# Create tables
def init_db():
    Base.metadata.create_all(bind=engine)

def save_post_to_db(post_data) -> bool:
    session = SessionLocal()
    try:
        # Check if post already exists
        existing = session.query(DBPost).filter(DBPost.post_id == post_data.post_id).first()
        if existing:
            return False
        
        db_post = DBPost(
            post_id=post_data.post_id,
            platform=post_data.platform,
            text=post_data.text,
            author_id=post_data.author_id,
            author_name=post_data.author_name,
            published_at=post_data.published_at,
            url=post_data.url,
            threat_score=post_data.threat_score,
            threat_label=post_data.threat_label,
            sentiment_score=post_data.sentiment_score,
            flagged=post_data.flagged,
            processed_at=post_data.processed_at,
            engagement=post_data.engagement
        )
        session.add(db_post)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"[Database] Error saving post {post_data.post_id}: {e}")
        return False
    finally:
        session.close()

def purge_expired_records(retention_days: int = 7):
    """
    Cost Optimization:
    Purges all posts whose published_at date is older than retention_days.
    """
    session = SessionLocal()
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)
        deleted_count = session.query(DBPost).filter(
            DBPost.published_at < cutoff
        ).delete()
        
        session.commit()
        if deleted_count > 0:
            print(f"[Database Purge] Cleaned up {deleted_count} expired posts (older than {retention_days} days).")
    except Exception as e:
        session.rollback()
        print(f"[Database Purge] Error performing purge: {e}")
    finally:
        session.close()

class DBHostileChannel(Base):
    __tablename__ = "hostile_channels"

    id = Column(Integer, primary_key=True, index=True)
    author_id = Column(String, unique=True, index=True, nullable=False)
    author_name = Column(String, nullable=False)
    platform = Column(String, index=True, nullable=False)
    threat_count = Column(Integer, default=0)
    avg_threat_score = Column(Float, default=0.0)
    status = Column(String, default="active_monitoring")

def update_hostile_channel(author_id: str, author_name: str, platform: str, threat_score: float):
    session = SessionLocal()
    try:
        existing = session.query(DBHostileChannel).filter(DBHostileChannel.author_id == author_id).first()
        if existing:
            new_count = existing.threat_count + 1
            existing.avg_threat_score = ((existing.avg_threat_score * existing.threat_count) + threat_score) / new_count
            existing.threat_count = new_count
        else:
            new_channel = DBHostileChannel(
                author_id=author_id,
                author_name=author_name,
                platform=platform,
                threat_count=1,
                avg_threat_score=threat_score,
                status="active_monitoring"
            )
            session.add(new_channel)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[Database] Error updating hostile channel {author_id}: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    init_db()
    print("[Database] Setup initialized successfully.")
