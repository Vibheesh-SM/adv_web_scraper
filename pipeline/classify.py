import os
import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv
from pipeline.schema import Post
from pipeline.pre_filter import should_process_post

load_dotenv()

# Lazy load classifier to prevent blocking startup / import times
_classifier = None
_model_loaded = False

def get_classifier():
    global _classifier, _model_loaded
    if _model_loaded:
        return _classifier
        
    use_ai = os.getenv("USE_AI_CLASSIFIER", "true").lower() in ("true", "1", "yes")
    if not use_ai:
        print("[AI Classifier] AI Classifier is disabled via USE_AI_CLASSIFIER. Using rule-based fallback.")
        _classifier = None
        _model_loaded = True
        return _classifier

    try:
        from transformers import pipeline
        import torch
        # Restrict threads to prevent CPU spikes in multi-threaded environments
        torch.set_num_threads(1)
        
        print("[AI Classifier] Loading zero-shot model valhalla/distilbart-mnli-12-1 on CPU...")
        # Use distilbart-mnli-12-1 which is 3x smaller and faster than bart-large-mnli
        _classifier = pipeline("zero-shot-classification", model="valhalla/distilbart-mnli-12-1", device=-1)
    except Exception as e:
        print(f"[AI Classifier] HF Transformers not loaded ({e}). Using rule-based fallback.")
        _classifier = None
    _model_loaded = True
    return _classifier

THREAT_LABELS = ["smear_campaign", "coordinated_attack", "misinformation", "satire_or_parody", "supportive_mention", "neutral_mention"]

def classify_and_score(post: Post) -> Post:
    """
    Analyzes a Post, computes sentiment and intent classification,
    and returns a post with threat_score, threat_label, and processed_at.
    """
    post.processed_at = datetime.datetime.now(datetime.timezone.utc)
    
    # 1. Pre-filter check
    should_classify, sentiment = should_process_post(post)
    post.sentiment_score = sentiment
    
    if not should_classify:
        # Save compute: immediately classify as neutral
        post.threat_label = "positive_sentiment" if sentiment > 0.4 else "neutral_mention"
        post.threat_score = max(0.0, 0.1 - (sentiment * 0.1)) # very low threat
        post.flagged = False
        return post

    # 2. Perform intent classification
    classification_scores = {}
    clf = get_classifier()
    if clf:
        try:
            res = clf(post.text, candidate_labels=THREAT_LABELS)
            classification_scores = dict(zip(res["labels"], res["scores"]))
        except Exception as e:
            print(f"[AI Classifier] Inference error: {e}. Falling back to rule-based classification.")
            classification_scores = get_rule_based_scores(post.text)
    else:
        classification_scores = get_rule_based_scores(post.text)

    # 3. Determine the primary threat label
    # Find the label with highest probability
    best_label = max(classification_scores, key=classification_scores.get)
    best_prob = classification_scores[best_label]
    
    post.threat_label = best_label
    
    # 4. Compute composite threat score:
    # 50% Intent Classification Probability
    # 25% Sentiment Penalty (more negative sentiment -> higher threat)
    # 25% Engagement weight (more likes/shares -> higher propagation risk)
    intent_part = best_prob * 0.50
    
    # Sentiment penalty: scale compound (-1 to 1) to (1 to 0) threat influence
    sentiment_part = ((1.0 - sentiment) / 2.0) * 0.25
    
    # Simple propagation risk: scale total engagement up to a cap
    engagement_count = sum(post.engagement.values()) if post.engagement else 0
    engagement_part = min(0.25, (engagement_count / 1000.0) * 0.25)
    
    # If the label itself is neutral or supportive, cap the threat score
    if best_label in ("neutral_mention", "supportive_mention"):
        post.threat_score = min(0.30, intent_part + sentiment_part + engagement_part)
    else:
        post.threat_score = min(1.0, intent_part + sentiment_part + engagement_part)
        
    # Flag posts crossing the 0.80 threshold
    post.flagged = post.threat_score >= 0.80
    
    # Mocking embedding for storage (free tier optimization - simple tf-idf or hash)
    # 384 dimensions matching all-MiniLM-L6-v2 schema
    post.embedding = [0.0] * 384 
    
    return post

def get_rule_based_scores(text: str) -> Dict[str, float]:
    """
    A fast, dependency-free regex classification fallback.
    """
    text_lower = text.lower()
    scores = {label: 0.1 for label in THREAT_LABELS}
    
    # Quick keyword patterns containing localized English, Tamil script, and Tanglish transliterated terms
    smear_keywords = [
        "scam", "corrupt", "hacked", "stole", "steal", "garbage", "trash", "fraud", "hate", "worst",
        "ஏமாற்று", "ஊழல்", "துரோகி", "பொய்", "கோமாளி", "பித்தலாட்டம்", "அயோக்கியன்", "பிராடு", "அவதூறு", "திருடன்", "திருட்டு",
        "yeamatru", "yemathuran", "oolal", "uzhal", "dhrogam", "throgam", "throgi", "dhrogi", "poi", "poiya", "komali", 
        "ayokkian", "ayogiyan", "fraadu", "thirudan", "thiruttu", "sangi", "sanghi"
    ]
    cib_keywords = ["bot", "coordinated", "spam", "paid hack", "fake account", "குழு", "கூட்டணி", "பரப்புரை", "paid troll"]
    misinfo_keywords = ["fake news", "conspiracy", "secret", "exposed", "truth behind", "சதி", "ரகசியம்", "உண்மை"]
    support_keywords = [
        "support", "victory", "best", "great", "leader", "vote", "growth", "integrity", "honest",
        "வாழ்த்துக்கள்", "சிங்கம்", "தலைவர்", "நம்பிக்கை", "வீரம்", "வெற்றி", "ஆதரவு",
        "valthukal", "vaalthukal", "singam", "thalaivar", "thalaiva", "nambikai", "vetri", "aatharavu", "congrats"
    ]
    
    smear_count = sum(1 for kw in smear_keywords if kw in text_lower)
    cib_count = sum(1 for kw in cib_keywords if kw in text_lower)
    misinfo_count = sum(1 for kw in misinfo_keywords if kw in text_lower)
    support_count = sum(1 for kw in support_keywords if kw in text_lower)
    
    if smear_count > 0:
        scores["smear_campaign"] = 0.7 + (0.05 * smear_count)
    if cib_count > 0:
        scores["coordinated_attack"] = 0.7 + (0.05 * cib_count)
    if misinfo_count > 0:
        scores["misinformation"] = 0.6 + (0.05 * misinfo_count)
    if support_count > 0:
        scores["supportive_mention"] = 0.7 + (0.05 * support_count)
        
    # Normalize probabilities
    total = sum(scores.values())
    for k in scores:
        scores[k] /= total
        
    return scores

if __name__ == "__main__":
    test_post = Post(
        post_id="test_inference",
        platform="twitter",
        text="WARNING: organization_name is committing fraud and scamming people out of their money!",
        author_id="a1",
        author_name="Alerts",
        published_at=datetime.datetime.now(datetime.timezone.utc),
        url="http://x.com/post"
    )
    res = classify_and_score(test_post)
    print(f"Text: {res.text}")
    print(f"Threat Label: {res.threat_label} | Score: {res.threat_score:.4f} | Sentiment: {res.sentiment_score:.4f} | Flagged: {res.flagged}")
