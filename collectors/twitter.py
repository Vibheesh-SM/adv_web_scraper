import os
import datetime
import urllib.parse
import feedparser
from typing import List
from dotenv import load_dotenv
from pipeline.schema import Post

load_dotenv()

TARGET_KEYWORDS = os.getenv("TARGET_KEYWORDS", "organization_name").split(",")
# Public Nitter instances can be rotated or custom defined
NITTER_BASE_URL = os.getenv("NITTER_INSTANCE", "https://nitter.net")

def fetch_twitter_threats(custom_keywords: List[str] = None) -> List[Post]:
    print("[Twitter Collector] Querying public feeds...")
    posts = []
    
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    
    for kw in target_kws:
        kw_clean = kw.strip()
        encoded_kw = urllib.parse.quote(kw_clean)
        
        # Free search parsing using Nitter's RSS feed
        rss_url = f"{NITTER_BASE_URL}/search/rss?q={encoded_kw}"
        
        try:
            print(f"[Twitter Collector] Fetching RSS feed for: {kw_clean}")
            feed = feedparser.parse(rss_url)
            
            # If feed returned error or is empty, we fall back to mock data
            if not feed.entries:
                allow_mock = os.getenv("ALLOW_MOCK_DATA", "true").lower() in ("true", "1", "yes")
                if not allow_mock:
                    print(f"[Twitter Collector] No feed entries found and Mock data is disabled. Skipping.")
                    return []
                print(f"[Twitter Collector] No feed entries found or Nitter instance is rate-limiting. Using mock fallback.")
                return generate_mock_posts(custom_keywords=target_kws)
                
            for entry in feed.entries:
                # Parse author handle from Nitter titles, e.g. "AuthorName (@handle)"
                author_display = entry.get("author", "Anonymous")
                author_id = author_display.split(" ")[-1].strip("()") if "@" in author_display else author_display
                
                # Check for publication timestamp
                pub_parsed = entry.get("published_parsed")
                if pub_parsed:
                    published_at = datetime.datetime(*pub_parsed[:6], tzinfo=datetime.timezone.utc)
                else:
                    published_at = datetime.datetime.now(datetime.timezone.utc)
                
                post_id = entry.id.split("/")[-1].split("#")[0] if hasattr(entry, "id") else f"tw_{hash(entry.link)}"
                
                post = Post(
                    post_id=post_id,
                    platform="twitter",
                    text=entry.summary if hasattr(entry, "summary") else entry.title,
                    author_id=author_id,
                    author_name=author_display,
                    published_at=published_at,
                    url=entry.link if hasattr(entry, "link") else f"https://twitter.com/i/web/status/{post_id}"
                )
                posts.append(post)
                
        except Exception as e:
            allow_mock = os.getenv("ALLOW_MOCK_DATA", "true").lower() in ("true", "1", "yes")
            if not allow_mock:
                print(f"[Twitter Collector] Error parsing RSS feed: {e}. Mock data is disabled. Skipping.")
                return []
            print(f"[Twitter Collector] Error parsing RSS feed: {e}. Defaulting to mock posts.")
            return generate_mock_posts(custom_keywords=target_kws)
            
    return posts

def generate_mock_posts(custom_keywords: List[str] = None) -> List[Post]:
    now = datetime.datetime.now(datetime.timezone.utc)
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    raw_kw = target_kws[0].strip() if target_kws else "organization_name"
    tag_fmt = f"#{raw_kw.lstrip('#')}" if raw_kw.replace('#','').isalnum() else raw_kw
    return [
        Post(
            post_id=f"tw_mock_{hash(raw_kw)}1",
            platform="twitter",
            text=f"The discussion around {tag_fmt} ({raw_kw}) has been growing online. Real development and active public updates.",
            author_id="supporter_x",
            author_name="Supporter X (@supporter_x)",
            published_at=now - datetime.timedelta(hours=2),
            url="https://twitter.com/supporter_x/status/mock102"
        ),
        Post(
            post_id=f"tw_mock_{hash(raw_kw)}2",
            platform="twitter",
            text=f"Critical updates regarding {tag_fmt}. People are questioning the statements made under {raw_kw} today.",
            author_id="critic_y",
            author_name="Critic Y (@critic_y)",
            published_at=now - datetime.timedelta(minutes=15),
            url="https://twitter.com/critic_y/status/mock103"
        )
    ]

if __name__ == "__main__":
    results = fetch_twitter_threats()
    for post in results:
        print(f"[{post.platform.upper()}] Post ID: {post.post_id} | Author: {post.author_name} | Text: {post.text[:80]}...")
