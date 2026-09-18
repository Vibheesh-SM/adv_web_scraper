import os
import datetime
import urllib.parse
import feedparser
from typing import List
from dotenv import load_dotenv
from pipeline.schema import Post

load_dotenv()

TARGET_KEYWORDS = os.getenv("TARGET_KEYWORDS", "organization_name").split(",")

# Specific Tamil news portals to monitor
NEWS_DOMAINS = [
    "puthiyathalaimurai.com",
    "vikatan.com",
    "thanthitv.com",
    "dinamalar.com",
    "polimernews.com",
    "tamil.oneindia.com",
    "dinakaran.com"
]

from concurrent.futures import ThreadPoolExecutor

def fetch_chunk(chunk: List[str], site_query: str) -> List[Post]:
    posts = []
    kw_query = " OR ".join([f'"{kw.strip()}"' for kw in chunk if kw.strip()])
    if not kw_query:
        return posts
        
    full_query = f"({kw_query}) ({site_query})"
    encoded_query = urllib.parse.quote(full_query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}"
    
    try:
        print(f"[Main Media Collector] Querying RSS feed for batch query: {kw_query}")
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries[:50]: # Limit to top 50 news articles
            title = entry.title
            publisher = "Tamil Main Media"
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title_text = parts[0]
                publisher = parts[1]
            else:
                title_text = title
                
            pub_parsed = entry.get("published_parsed")
            if pub_parsed:
                published_at = datetime.datetime(*pub_parsed[:6], tzinfo=datetime.timezone.utc)
            else:
                published_at = datetime.datetime.now(datetime.timezone.utc)
                
            post_id = f"media_{hash(entry.link)}"
            
            post = Post(
                post_id=post_id,
                platform="main_media",
                text=f"Outlet: {publisher}. Headline: {title_text}. Summary: {entry.summary if hasattr(entry, 'summary') else ''}",
                author_id=publisher.lower().replace(" ", "_"),
                author_name=publisher,
                published_at=published_at,
                url=entry.link if hasattr(entry, "link") else ""
            )
            posts.append(post)
            
    except Exception as e:
        print(f"[Main Media Collector] Error parsing RSS feed: {e}")
        
    return posts

def fetch_main_media_threats(custom_keywords: List[str] = None) -> List[Post]:
    print("[Main Media Collector] Fetching specific Tamil news outlets concurrently...")
    posts = []
    
    # Construct domain restriction query string
    site_query = " OR ".join([f"site:{domain}" for domain in NEWS_DOMAINS])
    
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    
    # Chunk keywords in groups of 3 for higher specificity
    chunks = [target_kws[i:i + 3] for i in range(0, len(target_kws), 3)]
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(lambda c: fetch_chunk(c, site_query), chunks)
        for res in results:
            posts.extend(res)
            
    return posts

if __name__ == "__main__":
    results = fetch_main_media_threats()
    for post in results:
        print(f"[{post.platform.upper()}] Post ID: {post.post_id} | Author: {post.author_name} | Text: {post.text[:80]}...")
