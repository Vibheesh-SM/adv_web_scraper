import os
import datetime
import json
import re
import urllib.parse
import httpx
from typing import List, Dict, Any
from googleapiclient.discovery import build
import redis
from dotenv import load_dotenv
from pipeline.schema import Post

load_dotenv()

# Redis initialization for rate limits/quota tracking
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

try:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
except Exception:
    r = None

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
TARGET_KEYWORDS = os.getenv("TARGET_KEYWORDS", "organization_name").split(",")

# Daily quota limits (YouTube free tier allows 10,000 units/day)
MAX_DAILY_QUOTA = 9500 
SEARCH_COST = 100
COMMENT_THREAD_COST = 1

MAX_POST_AGE_DAYS = int(os.getenv("MAX_POST_AGE_DAYS", "3"))

def get_today_quota_key() -> str:
    today_str = datetime.date.today().isoformat()
    return f"quota:youtube:{today_str}"

def get_current_quota_spent() -> int:
    if not r:
        return 0
    quota = r.get(get_today_quota_key())
    return int(quota) if quota else 0

def increment_quota(amount: int):
    if not r:
        return
    key = get_today_quota_key()
    r.incrby(key, amount)
    r.expire(key, 86400) # 24 hour TTL

def is_quota_available(cost: int) -> bool:
    return (get_current_quota_spent() + cost) <= MAX_DAILY_QUOTA

def find_video_renderers(data):
    results = []
    if isinstance(data, dict):
        if "videoRenderer" in data:
            results.append(data["videoRenderer"])
        for k, v in data.items():
            results.extend(find_video_renderers(v))
    elif isinstance(data, list):
        for item in data:
            results.extend(find_video_renderers(item))
    return results

def parse_relative_time(time_str: str) -> datetime.datetime:
    old_epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    if not time_str:
        return old_epoch
        
    cleaned = re.sub(r"\s+", " ", time_str.lower().replace("\xa0", " ").strip())
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # 1. Handle active live streams ONLY (must not be a past streamed event like "Streamed 2 days ago")
    if ("watching" in cleaned or cleaned in ("live", "live now")) and "ago" not in cleaned and "streamed" not in cleaned:
        return now
        
    # 2. Handle yesterday
    if "yesterday" in cleaned:
        return now - datetime.timedelta(days=1)
        
    # 3. Match relative times with "ago" (e.g. "2 years ago", "4d ago", "7h ago", "31 min ago", "1mo ago", "Streamed 2y ago")
    match = re.search(
        r"(\d+)\s*(seconds?|sec|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|wks?|w|months?|mos?|mo|years?|yrs?|y)\s+ago",
        cleaned
    )
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        
        if unit in ("s", "sec", "second", "seconds"):
            return now - datetime.timedelta(seconds=amount)
        elif unit in ("m", "min", "mins", "minute", "minutes"):
            return now - datetime.timedelta(minutes=amount)
        elif unit in ("h", "hr", "hrs", "hour", "hours"):
            return now - datetime.timedelta(hours=amount)
        elif unit in ("d", "day", "days"):
            return now - datetime.timedelta(days=amount)
        elif unit in ("w", "wk", "wks", "week", "weeks"):
            return now - datetime.timedelta(weeks=amount)
        elif unit in ("mo", "mos", "month", "months"):
            return now - datetime.timedelta(days=amount * 30)
        elif unit in ("y", "yr", "yrs", "year", "years"):
            return now - datetime.timedelta(days=amount * 365)

    # 4. Handle absolute date strings like "Premiered Apr 1, 2024", "Streamed live on Jan 15, 2023", "May 5, 2024"
    date_clean = re.sub(r"^(premiered|streamed live on|streamed on|uploaded on)\s+", "", cleaned)
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%b %d %Y"):
        try:
            dt = datetime.datetime.strptime(date_clean.strip(), fmt)
            return dt.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            pass

    # Safe fallback: Defaulting to old_epoch guarantees old/unparseable videos never bypass the search window
    return old_epoch

from concurrent.futures import ThreadPoolExecutor

def fetch_chunk(chunk: List[str], headers: dict) -> List[Post]:
    posts = []
    kw_query = " OR ".join([f'"{kw.strip()}"' for kw in chunk if kw.strip()])
    if not kw_query:
        return posts
        
    encoded_kw = urllib.parse.quote(kw_query)
    # sp=CAI%3D sorts by upload date, hl=en forces English language results
    url = f"https://www.youtube.com/results?search_query={encoded_kw}&sp=CAI%3D&hl=en"
    
    max_age_days = int(os.getenv("MAX_POST_AGE_DAYS", "3"))
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
    
    try:
        print(f"[YouTube Collector] Scraping public search page for batch query: {kw_query}")
        with httpx.Client(headers=headers, timeout=10.0) as client:
            response = client.get(url)
            if response.status_code != 200:
                return posts
                
            # Extract ytInitialData json object
            match = re.search(r"ytInitialData\s*=\s*({.+?});", response.text)
            if not match:
                return posts
                
            data = json.loads(match.group(1))
            renderers = find_video_renderers(data)
            
            for renderer in renderers[:50]: # Limit to top 50 matches per batch
                video_id = renderer.get("videoId")
                if not video_id:
                    continue
                    
                # Extract title text safely
                title_runs = renderer.get("title", {}).get("runs", [])
                title = title_runs[0].get("text", "") if title_runs else ""
                
                # Extract description snippet safely
                desc_runs = renderer.get("descriptionSnippet", {}).get("runs", [])
                desc = desc_runs[0].get("text", "") if desc_runs else ""
                
                # Owner channel name
                owner_runs = renderer.get("ownerText", {}).get("runs", [])
                owner_name = owner_runs[0].get("text", "Unknown Channel") if owner_runs else "Unknown Channel"
                
                # Channel ID
                channel_id = "unknown"
                if owner_runs:
                    browse_endpoint = owner_runs[0].get("navigationEndpoint", {}).get("browseEndpoint", {})
                    channel_id = browse_endpoint.get("browseId", "unknown")
                    
                # Views count
                views_text = renderer.get("viewCountText", {}).get("simpleText", "0 views")
                views = 0
                try:
                    digits = re.sub(r"\D", "", views_text)
                    if digits:
                        views = int(digits)
                except ValueError:
                    pass
                    
                # Extract relative time string safely from simpleText or runs
                pub_obj = renderer.get("publishedTimeText", {})
                time_text = pub_obj.get("simpleText", "")
                if not time_text:
                    runs = pub_obj.get("runs", [])
                    if runs:
                        time_text = runs[0].get("text", "")
                        
                badges = [b.get("metadataBadgeRenderer", {}).get("label", "") for b in renderer.get("badges", [])]
                if "LIVE" in badges and not time_text:
                    published_at = datetime.datetime.now(datetime.timezone.utc)
                else:
                    published_at = parse_relative_time(time_text)
                    
                # Enforce sliding search window: Skip videos older than MAX_POST_AGE_DAYS
                if published_at < cutoff_date:
                    continue
                    
                post = Post(
                    post_id=f"yt_vid_{video_id}",
                    platform="youtube",
                    text=f"Video Title: {title}. Description: {desc}",
                    author_id=channel_id,
                    author_name=owner_name,
                    published_at=published_at,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    engagement={"views": views},
                    raw_json=None
                )
                posts.append(post)
    except Exception as e:
        print(f"[YouTube Collector] Error scraping public page for batch: {e}")
        
    return posts

def scrape_youtube_public(custom_keywords: List[str] = None) -> List[Post]:
    print("[YouTube Collector] Scraping public search page concurrently...")
    posts = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    # Load hostile YouTube channels to actively track their uploads
    hostile_queries = []
    try:
        from database.database import SessionLocal, DBHostileChannel
        session = SessionLocal()
        hostile_chans = session.query(DBHostileChannel).filter(
            DBHostileChannel.platform == "youtube",
            DBHostileChannel.status == "active_monitoring"
        ).all()
        for chan in hostile_chans:
            if chan.author_name:
                hostile_queries.append(f'"{chan.author_name.strip()}"')
        session.close()
    except Exception as e:
        print(f"[YouTube Collector] Error loading hostile channels from DB: {e}")
        
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    all_queries = list(set([kw.strip() for kw in target_kws if kw.strip()] + hostile_queries))
    
    # Chunk queries in groups of 2 for higher specificity
    chunks = [all_queries[i:i + 2] for i in range(0, len(all_queries), 2)]
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(lambda c: fetch_chunk(c, headers), chunks)
        for res in results:
            posts.extend(res)
            
    # Final filter pass to ensure every single post strictly satisfies the search window
    max_age_days = int(os.getenv("MAX_POST_AGE_DAYS", "3"))
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
    filtered_posts = []
    for p in posts:
        pub = p.published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=datetime.timezone.utc)
        if pub >= cutoff:
            filtered_posts.append(p)
            
    return filtered_posts

def fetch_youtube_threats(custom_keywords: List[str] = None) -> List[Post]:
    print("[YouTube Collector] Starting YouTube Threat Scans...")
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    
    if not YOUTUBE_API_KEY or YOUTUBE_API_KEY == "your_youtube_api_key_here":
        print("[YouTube Collector] YOUTUBE_API_KEY is not set. Falling back to public page scraper...")
        scraped_posts = scrape_youtube_public(custom_keywords=target_kws)
        if scraped_posts:
            return scraped_posts
            
        allow_mock = os.getenv("ALLOW_MOCK_DATA", "true").lower() in ("true", "1", "yes")
        if not allow_mock:
            print("[YouTube Collector] Public scraper returned no posts and Mock data is disabled. Skipping.")
            return []
        print("[YouTube Collector] Public scraper failed. Generating mock/simulation data.")
        return generate_mock_posts(custom_keywords=target_kws)

    if not is_quota_available(SEARCH_COST):
        print(f"[YouTube Collector] ERROR: Daily quota limit ({MAX_DAILY_QUOTA} units) reached. Skipping.")
        return []

    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        posts = []
        
        max_age_days = int(os.getenv("MAX_POST_AGE_DAYS", "3"))
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
        published_after_rfc3339 = cutoff_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        for kw in target_kws:
            kw = kw.strip()
            if not is_quota_available(SEARCH_COST):
                break
            
            # 1. Search videos with upload date ordering and publishedAfter filter
            search_response = youtube.search().list(
                q=kw,
                part="id,snippet",
                maxResults=10,
                type="video",
                order="date",
                publishedAfter=published_after_rfc3339
            ).execute()
            increment_quota(SEARCH_COST)

            for item in search_response.get("items", []):
                video_id = item["id"]["videoId"]
                video_title = item["snippet"]["title"]
                channel_title = item["snippet"]["channelTitle"]
                channel_id = item["snippet"]["channelId"]
                published_at_str = item["snippet"]["publishedAt"]
                published_at = datetime.datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
                
                # Skip any video published earlier than the cutoff window
                if published_at < cutoff_date:
                    continue

                # Create Post object for the video description/title
                video_post = Post(
                    post_id=f"yt_vid_{video_id}",
                    platform="youtube",
                    text=f"Video Title: {video_title}. Description: {item['snippet']['description']}",
                    author_id=channel_id,
                    author_name=channel_title,
                    author_follower_count=0, # Need channel API for this (extra quota cost), skipping to save quota
                    published_at=published_at,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    engagement={"likes": 0, "comments": 0},
                    raw_json=item
                )
                posts.append(video_post)

                # 2. Fetch comments (thread lists cost 1 quota unit)
                if is_quota_available(COMMENT_THREAD_COST):
                    try:
                        comments_response = youtube.commentThreads().list(
                            videoId=video_id,
                            part="snippet",
                            maxResults=5
                        ).execute()
                        increment_quota(COMMENT_THREAD_COST)

                        for comment_item in comments_response.get("items", []):
                            comment_data = comment_item["snippet"]["topLevelComment"]["snippet"]
                            comment_id = comment_item["id"]
                            comment_text = comment_data["textOriginal"]
                            comment_author = comment_data["authorDisplayName"]
                            comment_author_id = comment_data.get("authorChannelId", {}).get("value", "unknown")
                            comment_pub_at = datetime.datetime.fromisoformat(comment_data["publishedAt"].replace("Z", "+00:00"))

                            comment_post = Post(
                                post_id=f"yt_comm_{comment_id}",
                                platform="youtube",
                                text=comment_text,
                                author_id=comment_author_id,
                                author_name=comment_author,
                                published_at=comment_pub_at,
                                url=f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
                                engagement={"likes": comment_data.get("likeCount", 0)},
                                raw_json=comment_item
                            )
                            posts.append(comment_post)
                    except Exception as e:
                        print(f"[YouTube Collector] Error fetching comments for video {video_id}: {e}")

        return posts

    except Exception as e:
        print(f"[YouTube Collector] Error executing API query: {e}")
        return []

def generate_mock_posts(custom_keywords: List[str] = None) -> List[Post]:
    # Returns simulated posts targeting organization/brand for testing purposes
    now = datetime.datetime.now(datetime.timezone.utc)
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    raw_kw = target_kws[0].strip() if target_kws else "organization_name"
    tag_fmt = f"#{raw_kw.lstrip('#')}" if raw_kw.replace('#','').isalnum() else raw_kw
    return [
        Post(
            post_id=f"yt_vid_mock_{hash(raw_kw)}1",
            platform="youtube",
            text=f"Exposing the truth behind {tag_fmt} ({raw_kw}). Detailed video breakdown on recent news!",
            author_id="UC_mock_channel_1",
            author_name="TruthSeeker99",
            published_at=now - datetime.timedelta(hours=1),
            url="https://www.youtube.com/watch?v=mock101",
            engagement={"likes": 420, "comments": 88}
        ),
        Post(
            post_id=f"yt_comm_mock_{hash(raw_kw)}2",
            platform="youtube",
            text=f"I agree with this analysis regarding {tag_fmt}. Real developments shown for {raw_kw}.",
            author_id="UC_mock_channel_2",
            author_name="UserBeta",
            published_at=now - datetime.timedelta(minutes=30),
            url="https://www.youtube.com/watch?v=mock101&lc=mock201",
            engagement={"likes": 15}
        )
    ]

def fetch_single_video_data(video_url: str, max_comments: int = 50) -> Dict[str, Any]:
    """
    Scrapes metadata for a single YouTube video without using the YouTube API,
    and returns a mock set of comments for analysis (since comments load dynamically).
    """
    print(f"[YouTube Collector] Scraping single video data for: {video_url}")
    
    # Extract video ID
    video_id = None
    if "v=" in video_url:
        match = re.search(r"v=([a-zA-Z0-9_-]+)", video_url)
        if match: video_id = match.group(1)
    elif "youtu.be/" in video_url:
        match = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", video_url)
        if match: video_id = match.group(1)
    else:
        video_id = video_url # Assume it's an ID if no match
        
    if not video_id:
        raise ValueError("Invalid YouTube URL or ID")
        
    url = f"https://www.youtube.com/watch?v={video_id}&hl=en"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }
    
    video_post = None
    try:
        with httpx.Client(headers=headers, timeout=10.0) as client:
            response = client.get(url)
            if response.status_code == 200:
                match = re.search(r"ytInitialData\s*=\s*({.+?});", response.text)
                if match:
                    data = json.loads(match.group(1))
                    
                    # Extract basic info
                    contents = data.get("contents", {}).get("twoColumnWatchNextResults", {}).get("results", {}).get("results", {}).get("contents", [])
                    
                    title = "Unknown Title"
                    channel_name = "Unknown Channel"
                    views = 0
                    
                    for item in contents:
                        if "videoPrimaryInfoRenderer" in item:
                            info = item["videoPrimaryInfoRenderer"]
                            title_runs = info.get("title", {}).get("runs", [])
                            if title_runs: title = title_runs[0].get("text", title)
                            
                            view_text = info.get("viewCount", {}).get("videoViewCountRenderer", {}).get("viewCount", {}).get("simpleText", "")
                            digits = re.sub(r"\D", "", view_text)
                            if digits: views = int(digits)
                            
                        if "videoSecondaryInfoRenderer" in item:
                            sec_info = item["videoSecondaryInfoRenderer"]
                            owner = sec_info.get("owner", {}).get("videoOwnerRenderer", {})
                            owner_runs = owner.get("title", {}).get("runs", [])
                            if owner_runs: channel_name = owner_runs[0].get("text", channel_name)
                    
                    # Extract likes if present
                    likes = 0
                    like_match = re.search(r'"label":\s*"([0-9,KMkm\.]+)\s+likes?"', response.text, re.IGNORECASE)
                    if not like_match:
                        like_match = re.search(r'([0-9,KMkm\.]+)\s+likes', response.text, re.IGNORECASE)
                    if like_match:
                        raw_likes = like_match.group(1).replace(",", "").strip().lower()
                        try:
                            if "k" in raw_likes:
                                likes = int(float(raw_likes.replace("k", "")) * 1000)
                            elif "m" in raw_likes:
                                likes = int(float(raw_likes.replace("m", "")) * 1000000)
                            else:
                                digits = re.sub(r"\D", "", raw_likes)
                                if digits: likes = int(digits)
                        except Exception:
                            likes = 0

                    video_post = Post(
                        post_id=f"yt_vid_{video_id}",
                        platform="youtube",
                        text=f"Video Title: {title}",
                        author_id="unknown_channel",
                        author_name=channel_name,
                        published_at=datetime.datetime.now(datetime.timezone.utc),
                        url=url,
                        engagement={"views": views, "likes": likes},
                        raw_json=None
                    )
    except Exception as e:
        print(f"[YouTube Collector] Error scraping video page: {e}")
        
    if not video_post:
        video_post = Post(
            post_id=f"yt_vid_{video_id}",
            platform="youtube",
            text="Video Title: Unknown (Scraping Failed)",
            author_id="unknown",
            author_name="Unknown Channel",
            published_at=datetime.datetime.now(datetime.timezone.utc),
            url=url,
            engagement={"views": 0, "likes": 0},
            raw_json=None
        )
        
    comments = []
    try:
        from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_POPULAR
        downloader = YoutubeCommentDownloader()
        # Fetch actual comments from the video
        generator = downloader.get_comments_from_url(url, sort_by=SORT_BY_POPULAR)
        
        count = 0
        for comment_dict in generator:
            if count >= max_comments:
                break
                
            text = comment_dict.get('text', '')
            author = comment_dict.get('author', 'Unknown')
            cid = comment_dict.get('cid', f"mock_{count}")
            votes_str = str(comment_dict.get('votes', '0')).replace(',', '').replace('.', '')
            try:
                votes = int(votes_str) if votes_str.isdigit() else 0
            except ValueError:
                votes = 0
                
            pub_time = datetime.datetime.now(datetime.timezone.utc)
            # time parsed from 'time' key could be relative, but for simplicity we use current time
            
            comments.append(Post(
                post_id=f"yt_comm_{video_id}_{cid}",
                platform="youtube",
                text=text,
                author_id=author,
                author_name=author,
                published_at=pub_time,
                url=f"{url}&lc={cid}",
                engagement={"likes": votes}
            ))
            count += 1
            
    except Exception as e:
        print(f"[YouTube Collector] Error fetching comments: {e}")
        
    return {
        "video": video_post,
        "comments": comments
    }

if __name__ == "__main__":
    results = fetch_youtube_threats()
    for post in results:
        print(f"[{post.platform.upper()}] Post ID: {post.post_id} | Author: {post.author_name} | Text: {post.text[:80]}...")
