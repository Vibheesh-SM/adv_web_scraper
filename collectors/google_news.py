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
    query = " OR ".join([f'"{kw.strip()}"' for kw in chunk if kw.strip()])
    if not query:
        return posts
        
    encoded_kw = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_kw}"
    try:
        print(f"[Google News Collector] Parsing RSS feed for batch query: {query}")
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries[:15]: # Limit to top 15 matches per chunk
            title = entry.title
            publisher = "Google News"
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
                
            post_id = f"news_{hash(entry.link)}"
            
            post = Post(
                post_id=post_id,
                platform="google_news",
                text=f"{title_text}. Summary: {entry.summary if hasattr(entry, 'summary') else ''}",
                author_id=publisher.lower().replace(" ", "_"),
                author_name=publisher,
                published_at=published_at,
                url=entry.link if hasattr(entry, 'link') else ""
            )
            posts.append(post)
            
    except Exception as e:
        print(f"[Google News Collector] Error parsing RSS feed for batch: {e}")
        
    return posts

def fetch_google_news_threats(custom_keywords: List[str] = None) -> List[Post]:
    print("[Google News Collector] Fetching news feeds concurrently...")
    posts = []
    
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    
    # Chunk keywords in groups of 10
    chunks = [target_kws[i:i + 10] for i in range(0, len(target_kws), 10)]
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(fetch_chunk, chunks)
        for res in results:
            posts.extend(res)
            
    return posts

if __name__ == "__main__":
    results = fetch_google_news_threats()
    for post in results:
        print(f"[{post.platform.upper()}] Post ID: {post.post_id} | Author: {post.author_name} | Text: {post.text[:80]}...")
