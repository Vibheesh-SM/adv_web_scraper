import os
import datetime
import httpx
from bs4 import BeautifulSoup
from typing import List
from dotenv import load_dotenv
from pipeline.schema import Post

load_dotenv()

# Specify list of public Telegram channels to scrape (comma separated names)
TELEGRAM_CHANNELS = [ch.strip() for ch in os.getenv("TELEGRAM_CHANNELS", "naam_tamilar_katchi").split(",") if ch.strip()]

def fetch_telegram_threats(custom_keywords: List[str] = None) -> List[Post]:
    print("[Telegram Collector] Scraping public channel previews...")
    posts = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 SocialMonitorPipeline/1.0"
    }
    
    # Load hostile Telegram channels to actively monitor
    hostile_telegram = []
    try:
        from database.database import SessionLocal, DBHostileChannel
        session = SessionLocal()
        hostile_chans = session.query(DBHostileChannel).filter(
            DBHostileChannel.platform == "telegram",
            DBHostileChannel.status == "active_monitoring"
        ).all()
        for chan in hostile_chans:
            if chan.author_id:
                hostile_telegram.append(chan.author_id.strip())
        session.close()
    except Exception as e:
        print(f"[Telegram Collector] Error loading hostile channels from DB: {e}")
        
    extra_channels = [kw.strip() for kw in custom_keywords if kw.strip()] if custom_keywords else []
    all_channels = list(set(TELEGRAM_CHANNELS + hostile_telegram + extra_channels))
    
    for channel in all_channels:
        url = f"https://t.me/s/{channel}"
        try:
            print(f"[Telegram Collector] Scraping channel: {channel}")
            with httpx.Client(headers=headers, timeout=10.0) as client:
                response = client.get(url)
                if response.status_code != 200:
                    print(f"[Telegram Collector] Failed to fetch channel {channel}: {response.status_code}")
                    continue
                    
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Fetch channel name/title
                channel_title_el = soup.find(class_="tgme_channel_info_header_title")
                channel_name = channel_title_el.get_text().strip() if channel_title_el else channel
                
                message_wraps = soup.find_all(class_="tgme_widget_message_wrap")
                
                for wrap in message_wraps[:50]: # Process top 50 recent messages from feed
                    # Message text
                    text_el = wrap.find(class_="tgme_widget_message_text")
                    if not text_el:
                        continue
                    text = text_el.get_text().strip()
                    
                    # Date/Time
                    time_el = wrap.find("time")
                    if time_el and time_el.has_attr("datetime"):
                        # Replace Z suffix with standard offset
                        published_at = datetime.datetime.fromisoformat(time_el["datetime"].replace("Z", "+00:00"))
                    else:
                        published_at = datetime.datetime.now(datetime.timezone.utc)
                        
                    # Message Link
                    link_el = wrap.find(class_="tgme_widget_message_date")
                    msg_url = link_el["href"] if link_el and link_el.has_attr("href") else f"https://t.me/{channel}"
                    
                    # Get message ID from link if possible
                    if link_el and link_el.has_attr("href"):
                        msg_id = f"tg_{channel}_{link_el['href'].split('/')[-1]}"
                    else:
                        msg_id = f"tg_{channel}_{hash(text)}"
                        
                    # Views/Engagement
                    views_el = wrap.find(class_="tgme_widget_message_views")
                    views = 0
                    if views_el:
                        views_text = views_el.get_text().strip()
                        # Clean suffix like K or M (e.g. 1.2K -> 1200)
                        try:
                            if "K" in views_text:
                                views = int(float(views_text.replace("K", "")) * 1000)
                            elif "M" in views_text:
                                views = int(float(views_text.replace("M", "")) * 1000000)
                            else:
                                views = int(views_text)
                        except ValueError:
                            pass
                            
                    post = Post(
                        post_id=msg_id,
                        platform="telegram",
                        text=f"Channel: @{channel}. Post: {text}",
                        author_id=channel.lower(),
                        author_name=channel_name,
                        published_at=published_at,
                        url=msg_url,
                        engagement={"views": views}
                    )
                    posts.append(post)
                    
        except Exception as e:
            print(f"[Telegram Collector] Error scraping channel {channel}: {e}")
            
    return posts

if __name__ == "__main__":
    results = fetch_telegram_threats()
    for post in results:
        print(f"[{post.platform.upper()}] Post ID: {post.post_id} | Author: {post.author_name} | Text: {post.text[:80]}...")
