import os
import sys
import datetime
from celery import Celery
from dotenv import load_dotenv

# Add project root to path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.database import SessionLocal, DBPost, init_db, purge_expired_records
from collectors.youtube import fetch_youtube_threats
from collectors.twitter import fetch_twitter_threats
from collectors.facebook import fetch_facebook_threats
from collectors.google_news import fetch_google_news_threats
from collectors.reddit import fetch_reddit_threats
from collectors.mastodon import fetch_mastodon_threats
from collectors.telegram import fetch_telegram_threats
from collectors.main_media import fetch_main_media_threats
from collectors.instagram import fetch_instagram_threats
from pipeline.classify import classify_and_score
from pipeline.pre_filter import should_process_post
from alerts.alerts import dispatch_alert

load_dotenv()

# Initialize Database Schema if not already done
init_db()

redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = os.getenv("REDIS_PORT", "6379")
celery_db = os.getenv("REDIS_CELERY_DB", "1")

broker_url = f"redis://{redis_host}:{redis_port}/{celery_db}"
result_backend = broker_url

celery_app = Celery("threat_intel", broker=broker_url, backend=result_backend)

# Configure Celery Beat schedules
celery_app.conf.beat_schedule = {
    "run-social-ingestion-every-30-minutes": {
        "task": "pipeline.celery_app.run_background_ingestion",
        "schedule": 1800.0, # Every 30 minutes in seconds
    },
}
celery_app.conf.timezone = "UTC"

@celery_app.task
def run_background_ingestion():
    print("[Celery Worker] Starting periodic threat ingestion and sentiment scanning...")
    
    # 1. Fetch raw posts from all collectors
    raw_posts = []
    try:
        raw_posts.extend(fetch_youtube_threats())
    except Exception as e:
        print(f"[Celery Ingestion] YouTube collector error: {e}")
        
    try:
        raw_posts.extend(fetch_twitter_threats())
    except Exception as e:
        print(f"[Celery Ingestion] Twitter collector error: {e}")
        
    try:
        raw_posts.extend(fetch_facebook_threats())
    except Exception as e:
        print(f"[Celery Ingestion] Facebook collector error: {e}")
        
    try:
        raw_posts.extend(fetch_google_news_threats())
    except Exception as e:
        print(f"[Celery Ingestion] Google News collector error: {e}")
        
    try:
        raw_posts.extend(fetch_reddit_threats())
    except Exception as e:
        print(f"[Celery Ingestion] Reddit collector error: {e}")
        
    try:
        raw_posts.extend(fetch_mastodon_threats())
    except Exception as e:
        print(f"[Celery Ingestion] Mastodon collector error: {e}")
        
    try:
        raw_posts.extend(fetch_telegram_threats())
    except Exception as e:
        print(f"[Celery Ingestion] Telegram collector error: {e}")
        
    try:
        raw_posts.extend(fetch_main_media_threats())
    except Exception as e:
        print(f"[Celery Ingestion] Main Media collector error: {e}")
        
    try:
        raw_posts.extend(fetch_instagram_threats())
    except Exception as e:
        print(f"[Celery Ingestion] Instagram collector error: {e}")
        
    # 2. Deduplicate raw_posts by post_id
    seen_ids = set()
    deduped_posts = []
    for post in raw_posts:
        if post.post_id not in seen_ids:
            seen_ids.add(post.post_id)
            deduped_posts.append(post)
    raw_posts = deduped_posts
    
    print(f"[Celery Worker] Found {len(raw_posts)} unique posts across all platforms. Processing...")
    
    session = SessionLocal()
    new_records = 0
    flagged_records = 0
    
    max_age_days = int(os.getenv("MAX_POST_AGE_DAYS", "3"))
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
    
    try:
        for rp in raw_posts:
            # Filter out posts older than the sliding window
            pub_at = rp.published_at
            if pub_at is not None:
                if pub_at.tzinfo is None:
                    pub_at = pub_at.replace(tzinfo=datetime.timezone.utc)
                if pub_at < cutoff_date:
                    continue

            # Verify political relevance (ignore unrelated noise/false matches)
            should_c, _ = should_process_post(rp)
            if not should_c:
                continue
                
            # Check database for existing items
            existing = session.query(DBPost).filter(DBPost.post_id == rp.post_id).first()
            if not existing:
                # Run classification
                scored_post = classify_and_score(rp)
                
                # Save post to database
                db_post = DBPost(
                    post_id=scored_post.post_id,
                    platform=scored_post.platform,
                    text=scored_post.text,
                    author_id=scored_post.author_id,
                    author_name=scored_post.author_name,
                    published_at=scored_post.published_at,
                    url=scored_post.url,
                    threat_score=scored_post.threat_score,
                    threat_label=scored_post.threat_label,
                    sentiment_score=scored_post.sentiment_score,
                    flagged=scored_post.flagged,
                    processed_at=scored_post.processed_at,
                    engagement=scored_post.engagement
                )
                session.add(db_post)
                new_records += 1
                
                if scored_post.flagged:
                    flagged_records += 1
                    # Dispatch notifications immediately
                    dispatch_alert(scored_post)
                    
        session.commit()
        
        # Purge records older than max_age_days
        purge_expired_records(retention_days=max_age_days)
        print(f"[Celery Worker] Ingestion task completed. Saved {new_records} new records ({flagged_records} flagged).")
        
    except Exception as e:
        session.rollback()
        print(f"[Celery Worker] Ingestion transaction failed: {e}")
    finally:
        session.close()
