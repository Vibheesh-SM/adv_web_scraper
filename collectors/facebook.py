import os
import datetime
import feedparser
from typing import List
from dotenv import load_dotenv
from pipeline.schema import Post

load_dotenv()

TARGET_KEYWORDS = os.getenv("TARGET_KEYWORDS", "organization_name").split(",")

import urllib.parse

from concurrent.futures import ThreadPoolExecutor

def fetch_chunk(chunk: List[str]) -> List[Post]:
    posts = []
    kw_query = " OR ".join([f'"{kw.strip()}"' for kw in chunk if kw.strip()])
    if not kw_query:
        return posts
        
    encoded_query = urllib.parse.quote(f"({kw_query}) site:facebook.com")
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}"
    
    try:
        print(f"[Facebook Collector] Querying RSS feed for batch query: {kw_query}")
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries[:15]: # Limit to top 15 matches per chunk
            title = entry.title
            publisher = "Facebook Public Post"
            
            pub_parsed = entry.get("published_parsed")
            if pub_parsed:
                published_at = datetime.datetime(*pub_parsed[:6], tzinfo=datetime.timezone.utc)
            else:
                published_at = datetime.datetime.now(datetime.timezone.utc)
                
            post_id = f"fb_{hash(entry.link)}"
            
            post = Post(
                post_id=post_id,
                platform="facebook",
                text=f"Facebook Mention: {title}",
                author_id="facebook_public",
                author_name=publisher,
                published_at=published_at,
                url=entry.link if hasattr(entry, "link") else ""
            )
            posts.append(post)
            
    except Exception as e:
        print(f"[Facebook Collector] Error parsing feed for batch: {e}")
        
    return posts

def fetch_facebook_threats(custom_keywords: List[str] = None) -> List[Post]:
    print("[Facebook Collector] Searching public page feeds concurrently...")
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
            print("[Facebook Collector] Real search returned no posts. Generating mock fallback.")
            return generate_mock_posts(custom_keywords=target_kws)
            
    return posts

def generate_mock_posts(custom_keywords: List[str] = None) -> List[Post]:
    now = datetime.datetime.now(datetime.timezone.utc)
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    kw = target_kws[0].strip() if target_kws else "organization_name"
    return [
        Post(
            post_id="fb_post_mock301",
            platform="facebook",
            text=f"The election campaign for {kw} is seeing incredible growth. They have the best integrity and leadership.",
            author_id="support_group_1",
            author_name="Grassroots Support Page",
            published_at=now - datetime.timedelta(hours=4),
            url="https://facebook.com/posts/mock301",
            engagement={"shares": 142, "likes": 50, "comments": 230}
        ),
        Post(
            post_id="fb_post_mock302",
            platform="facebook",
            text=f"Warning: Disinformation campaign spotted targeting {kw}. Someone posted a fake news document showing false claims.",
            author_id="public_discussion_board",
            author_name="Public Discussion Board Group",
            published_at=now - datetime.timedelta(hours=6),
            url="https://facebook.com/posts/mock302",
            engagement={"shares": 10, "likes": 2}
        )
    ]

if __name__ == "__main__":
    results = fetch_facebook_threats()
    for post in results:
        print(f"[{post.platform.upper()}] Post ID: {post.post_id} | Author: {post.author_name} | Text: {post.text[:80]}...")
