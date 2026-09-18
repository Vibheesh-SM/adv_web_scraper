import os
import datetime
import urllib.parse
import feedparser
from typing import List
from dotenv import load_dotenv
from pipeline.schema import Post

load_dotenv()

TARGET_KEYWORDS = os.getenv("TARGET_KEYWORDS", "organization_name").split(",")

from concurrent.futures import ThreadPoolExecutor

def fetch_chunk(chunk: List[str]) -> List[Post]:
    posts = []
    kw_query = " OR ".join([f'"{kw.strip()}"' for kw in chunk if kw.strip()])
    if not kw_query:
        return posts
        
    encoded_query = urllib.parse.quote(f"({kw_query}) site:instagram.com")
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}"
    
    try:
        print(f"[Instagram Collector] Querying RSS feed for batch query: {kw_query}")
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries[:15]: # Limit to top 15 matches per chunk
            title = entry.title
            publisher = "Instagram Public Post"
            
            pub_parsed = entry.get("published_parsed")
            if pub_parsed:
                published_at = datetime.datetime(*pub_parsed[:6], tzinfo=datetime.timezone.utc)
            else:
                published_at = datetime.datetime.now(datetime.timezone.utc)
                
            post_id = f"ig_{hash(entry.link)}"
            
            post = Post(
                post_id=post_id,
                platform="instagram",
                text=f"Instagram Mention: {title}",
                author_id="instagram_public",
                author_name=publisher,
                published_at=published_at,
                url=entry.link if hasattr(entry, "link") else ""
            )
            posts.append(post)
            
    except Exception as e:
        print(f"[Instagram Collector] Error parsing feed for batch: {e}")
        
    return posts

def fetch_instagram_threats(custom_keywords: List[str] = None) -> List[Post]:
    print("[Instagram Collector] Searching public page feeds concurrently...")
    posts = []
    
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    
    # Chunk keywords in groups of 10
    chunks = [target_kws[i:i + 10] for i in range(0, len(target_kws), 10)]
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(fetch_chunk, chunks)
        for res in results:
            posts.extend(res)
            
    # Fallback to mock data if feed parsing failed/returned nothing and mock is allowed
    if not posts:
        allow_mock = os.getenv("ALLOW_MOCK_DATA", "true").lower() in ("true", "1", "yes")
        if allow_mock:
            print("[Instagram Collector] Real search returned no posts. Generating mock fallback.")
            return generate_mock_posts(custom_keywords=target_kws)
            
    return posts

def generate_mock_posts(custom_keywords: List[str] = None) -> List[Post]:
    now = datetime.datetime.now(datetime.timezone.utc)
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    kw = target_kws[0].strip() if target_kws else "organization_name"
    if not kw.startswith("#") and kw.isalnum():
        hashtag_format = f"#{kw}"
    else:
        hashtag_format = kw
    return [
        Post(
            post_id="ig_post_mock401",
            platform="instagram",
            text=f"Check out this campaign video supporting {kw}. Absolute leadership goals.",
            author_id="supporter_ig_1",
            author_name="Insta Campaign Page",
            published_at=now - datetime.timedelta(hours=3),
            url="https://instagram.com/posts/mock401",
            engagement={"likes": 300, "comments": 45}
        ),
        Post(
            post_id="ig_post_mock402",
            platform="instagram",
            text=f"Warning: People are spreading misinformation about {kw} on Instagram stories today.",
            author_id="political_watch_ig",
            author_name="Political Watch India",
            published_at=now - datetime.timedelta(hours=5),
            url="https://instagram.com/posts/mock402",
            engagement={"likes": 120, "comments": 15}
        )
    ]

if __name__ == "__main__":
    results = fetch_instagram_threats()
    for post in results:
        print(f"[{post.platform.upper()}] Post ID: {post.post_id} | Author: {post.author_name} | Text: {post.text[:80]}...")
