import os
from typing import Tuple, List
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pipeline.schema import Post

load_dotenv()

# Load keywords from env
TARGET_KEYWORDS = [kw.strip().lower() for kw in os.getenv("TARGET_KEYWORDS", "organization_name").split(",")]

# Initialize VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()

import re
from sentence_transformers import SentenceTransformer, util

# Initialize Embedding Model once globally for semantic filtering
try:
    print("[Pre-Filter] Loading Semantic Vector Engine (all-MiniLM-L6-v2)...")
    semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
    # Tamil politics profile for similarity baseline
    reference_profile = "Naam Tamilar Katchi Seeman Tamil Nadu politics state elections dravidian farmer symbol"
    reference_embedding = semantic_model.encode(reference_profile, convert_to_tensor=True)
except Exception as e:
    print(f"[Pre-Filter] Could not load semantic model: {e}")
    semantic_model = None

def is_politically_relevant(text_lower: str) -> bool:
    # 1. Reject known noisy terms/false positives immediately
    noise_patterns = [
        r"aleksander\s+seeman", r"alexander\s+seeman", r"jordan\s+de\s+goey",
        r"craig\s+mcrae", r"afl", r"football", r"soccer"
    ]
    for pattern in noise_patterns:
        if re.search(pattern, text_lower):
            return False
            
    # 2. Strict Geo/Language Fencing
    if re.search(r"[\u0900-\u097F]", text_lower):
        return False
        
    # Reject out-of-state northern/national politics keywords common in national noise
    northern_politics = [
        "uttar pradesh", "up election", "up assembly", "lucknow", "yogi", "akhilesh",
        "himachal", "bihar", "punjab", "delhi election", "satta bajar",
        "bjp-congress", "bsp", "samajwadi", "west bengal", "bengal", "trinamool",
        "assembly elections 2027", "dd news", "the statesman"
    ]
    if any(np in text_lower for np in northern_politics):
        return False

    # 3. Fast-pass core NTK identity & known aliases (ensures valid NTK posts are never blocked)
    ntk_aliases = [
        "seeman", "ntk", "naam tamilar", "naam thamizhar", "vyavasayi", 
        "farmer symbol", "thambi", "senthamizhan", "katchi", "aamai", 
        "youtube party", "4 percent", "10 percent", "dravida", "annamalai vs"
    ]
    if any(alias in text_lower for alias in ntk_aliases):
        return True
        
    # 4. If no core keyword or alias is found, we enforce a highly strict semantic similarity
    if semantic_model is not None:
        try:
            post_emb = semantic_model.encode(text_lower, convert_to_tensor=True)
            cosine_score = util.cos_sim(reference_embedding, post_emb).item()
            
            # Require an extremely high match if no explicit NTK keywords are found
            if cosine_score < 0.45:
                return False
        except Exception:
            pass # Fallback to True if embedding fails
            
    return True

def calculate_hybrid_sentiment(text: str) -> float:
    text_lower = text.lower()
    
    # Calculate baseline English sentiment
    vs = analyzer.polarity_scores(text)
    score = vs['compound']
    
    # Localized Tamil & Tanglish threat keywords representing negative/abusive intent
    hostile_tamil = [
        "ஏமாற்று", "ஊழல்", "துரோகி", "பொய்", "கோமாளி", "பித்தலாட்டம்", "அயோக்கியன்", "பிராடு", "அவதூறு", "திருடன்", "திருட்டு",
        "yeamatru", "yemathuran", "oolal", "uzhal", "dhrogam", "throgam", "throgi", "dhrogi", "poi", "poiya", "komali", 
        "ayokkian", "ayogiyan", "fraadu", "thirudan", "thiruttu", "sangi", "sanghi"
    ]
    # Localized Tamil & Tanglish support keywords
    support_tamil = [
        "வாழ்த்துக்கள்", "சிங்கம்", "தலைவர்", "நம்பிக்கை", "வீரம்", "வெற்றி", "ஆதரவு",
        "valthukal", "vaalthukal", "singam", "thalaivar", "thalaiva", "nambikai", "vetri", "aatharavu", "congrats"
    ]
    
    hostile_count = sum(1 for kw in hostile_tamil if kw in text_lower)
    support_count = sum(1 for kw in support_tamil if kw in text_lower)
    
    score -= hostile_count * 0.15
    score += support_count * 0.15
    
    return max(-1.0, min(1.0, score))

def should_process_post(post: Post, custom_keywords: List[str] = None) -> Tuple[bool, float]:
    """
    Checks if a post is a candidate for deep threat classification.
    Returns (should_classify, sentiment_score).
    """
    text_lower = post.text.lower()
    
    # 1. Calculate hybrid sentiment score (English + Tamil + Tanglish)
    sentiment_score = calculate_hybrid_sentiment(post.text)
    
    # 2. If custom keywords are provided, check if post matches any custom keyword
    if custom_keywords:
        cleaned_kws = [k.strip().lower().lstrip("#") for k in custom_keywords if k.strip()]
        if any(kw in text_lower for kw in cleaned_kws):
            return True, sentiment_score

    # 3. Match keywords and verify political context relevance
    if not is_politically_relevant(text_lower):
        return False, sentiment_score
        
    return True, sentiment_score

if __name__ == "__main__":
    test_posts = [
        Post(post_id="t1", platform="twitter", text="I love this brand, they are doing amazing things!", author_id="u1", author_name="U1", published_at=None, url=""),
        Post(post_id="t2", platform="twitter", text="organization_name is complete garbage and scamming users.", author_id="u2", author_name="U2", published_at=None, url=""),
        Post(post_id="t3", platform="twitter", text="organization_name launched a new software update yesterday.", author_id="u3", author_name="U3", published_at=None, url="")
    ]
    
    for tp in test_posts:
        should_c, score = should_process_post(tp)
        print(f"Post: {tp.text[:50]}... | Should Deep Classify: {should_c} | Sentiment: {score}")
