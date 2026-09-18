import os
import datetime
import urllib.parse
import httpx
from typing import List
from dotenv import load_dotenv
from pipeline.schema import Post

load_dotenv()

TARGET_KEYWORDS = os.getenv("TARGET_KEYWORDS", "organization_name").split(",")

from concurrent.futures import ThreadPoolExecutor

def fetch_chunk(chunk: List[str], headers: dict) -> List[Post]:
    posts = []
    kw_query = " OR ".join([f'"{kw.strip()}"' for kw in chunk if kw.strip()])
    if not kw_query:
        return posts
        
    encoded_kw = urllib.parse.quote(kw_query)
    url = f"https://www.reddit.com/search.json?q={encoded_kw}&sort=new&limit=15"
    
    try:
        print(f"[Reddit Collector] Fetching posts for batch query: {kw_query}")
        with httpx.Client(headers=headers, timeout=10.0) as client:
            response = client.get(url)
            if response.status_code != 200:
                print(f"[Reddit Collector] Failed with status code {response.status_code}: {response.text[:200]}")
                return posts
                
            data = response.json()
            children = data.get("data", {}).get("children", [])
            
            for child in children:
                post_data = child.get("data", {})
                post_id = f"reddit_{post_data.get('id')}"
                title = post_data.get("title", "")
                selftext = post_data.get("selftext", "")
                subreddit = post_data.get("subreddit", "reddit")
                author = post_data.get("author", "unknown")
                created_utc = post_data.get("created_utc")
                permalink = post_data.get("permalink", "")
                
                if created_utc:
                    published_at = datetime.datetime.fromtimestamp(created_utc, tz=datetime.timezone.utc)
                else:
                    published_at = datetime.datetime.now(datetime.timezone.utc)
                    
                engagement = {
                    "likes": post_data.get("ups", 0),
                    "comments": post_data.get("num_comments", 0)
                }
                
                post = Post(
                    post_id=post_id,
                    platform="reddit",
                    text=f"Subreddit: r/{subreddit}. Title: {title}. Content: {selftext}",
                    author_id=author.lower(),
                    author_name=author,
                    published_at=published_at,
                    url=f"https://www.reddit.com{permalink}",
                    engagement=engagement
                )
                posts.append(post)
    except Exception as e:
        print(f"[Reddit Collector] Error querying Reddit for batch: {e}")
        
    return posts

def fetch_reddit_threats(custom_keywords: List[str] = None) -> List[Post]:
    print("[Reddit Collector] Querying public search API concurrently...")
    posts = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 SocialMonitorPipeline/1.0"
    }
    
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    
    # Chunk keywords in groups of 10
    chunks = [target_kws[i:i + 10] for i in range(0, len(target_kws), 10)]
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(lambda c: fetch_chunk(c, headers), chunks)
        for res in results:
            posts.extend(res)
            
    return posts

if __name__ == "__main__":
    results = fetch_reddit_threats()
    for post in results:
        print(f"[{post.platform.upper()}] Post ID: {post.post_id} | Author: {post.author_name} | Text: {post.text[:80]}...")
