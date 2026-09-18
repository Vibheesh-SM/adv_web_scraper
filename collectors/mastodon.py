import os
import datetime
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from typing import List
from dotenv import load_dotenv
from pipeline.schema import Post

load_dotenv()

TARGET_KEYWORDS = os.getenv("TARGET_KEYWORDS", "organization_name").split(",")

def clean_html(html_text: str) -> str:
    if not html_text:
        return ""
    try:
        # Use bs4 to strip html paragraph/link tags returned by Mastodon API
        return BeautifulSoup(html_text, "html.parser").get_text()
    except Exception:
        return html_text

def fetch_mastodon_threats(custom_keywords: List[str] = None) -> List[Post]:
    print("[Mastodon Collector] Fetching live public feeds...")
    posts = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 SocialMonitorPipeline/1.0"
    }
    
    target_kws = custom_keywords if custom_keywords and len(custom_keywords) > 0 else TARGET_KEYWORDS
    
    for kw in target_kws:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
            
        encoded_kw = urllib.parse.quote(kw_clean)
        url = f"https://mastodon.social/api/v2/search?q={encoded_kw}&type=statuses&limit=10"
        
        try:
            print(f"[Mastodon Collector] Fetching posts for keyword: {kw_clean}")
            with httpx.Client(headers=headers, timeout=10.0) as client:
                response = client.get(url)
                if response.status_code != 200:
                    print(f"[Mastodon Collector] Failed with status code {response.status_code}: {response.text[:200]}")
                    continue
                    
                data = response.json()
                statuses = data.get("statuses", [])
                
                for status in statuses:
                    status_id = f"mastodon_{status.get('id')}"
                    html_content = status.get("content", "")
                    clean_content = clean_html(html_content)
                    
                    account = status.get("account", {})
                    author_name = account.get("display_name", "") or account.get("username", "unknown")
                    author_id = account.get("username", "unknown").lower()
                    
                    created_at_str = status.get("created_at")
                    if created_at_str:
                        # Mastodon dates usually end with Z, e.g., '2023-07-27T14:28:50.000Z'
                        published_at = datetime.datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    else:
                        published_at = datetime.datetime.now(datetime.timezone.utc)
                        
                    engagement = {
                        "likes": status.get("favourites_count", 0),
                        "shares": status.get("reblogs_count", 0),
                        "comments": status.get("replies_count", 0)
                    }
                    
                    post = Post(
                        post_id=status_id,
                        platform="mastodon",
                        text=clean_content,
                        author_id=author_id,
                        author_name=author_name,
                        published_at=published_at,
                        url=status.get("url", ""),
                        engagement=engagement
                    )
                    posts.append(post)
                    
        except Exception as e:
            print(f"[Mastodon Collector] Error querying Mastodon for {kw_clean}: {e}")
            
    return posts

if __name__ == "__main__":
    results = fetch_mastodon_threats()
    for post in results:
        print(f"[{post.platform.upper()}] Post ID: {post.post_id} | Author: {post.author_name} | Text: {post.text[:80]}...")
