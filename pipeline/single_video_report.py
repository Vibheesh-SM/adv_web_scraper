import datetime
import io
import re
from typing import List, Dict, Any, Tuple
from pipeline.schema import Post

def compute_single_video_metrics(video_post: Post, processed_comments: List[Post]) -> Dict[str, Any]:
    """
    Computes aggregated threat, sentiment, and engagement metrics for a single analyzed video.
    """
    total_comments = len(processed_comments)
    video_title = video_post.text.replace("Video Title: ", "").strip()
    channel_name = video_post.author_name
    video_views = video_post.engagement.get("views", 0) if video_post.engagement else 0
    video_likes = video_post.engagement.get("likes", 0) if video_post.engagement else 0
    
    total_comment_likes = sum(c.engagement.get("likes", 0) for c in processed_comments) if processed_comments else 0
    max_comment_likes = max([c.engagement.get("likes", 0) for c in processed_comments], default=0)
    
    avg_threat = (sum(c.threat_score or 0.0 for c in processed_comments) / total_comments) if total_comments > 0 else 0.0
    avg_sentiment = (sum(c.sentiment_score or 0.0 for c in processed_comments) / total_comments) if total_comments > 0 else 0.0
    
    critical_comments = [c for c in processed_comments if (c.threat_score or 0.0) >= 0.80]
    high_comments = [c for c in processed_comments if 0.50 <= (c.threat_score or 0.0) < 0.80]
    moderate_comments = [c for c in processed_comments if 0.30 <= (c.threat_score or 0.0) < 0.50]
    low_comments = [c for c in processed_comments if (c.threat_score or 0.0) < 0.30]
    
    # Label breakdown
    label_counts: Dict[str, int] = {}
    for c in processed_comments:
        lbl = c.threat_label or "neutral_mention"
        label_counts[lbl] = label_counts.get(lbl, 0) + 1
        
    # Sentiment buckets
    positive_comments = [c for c in processed_comments if (c.sentiment_score or 0.0) > 0.15]
    neutral_comments = [c for c in processed_comments if -0.15 <= (c.sentiment_score or 0.0) <= 0.15]
    negative_comments = [c for c in processed_comments if (c.sentiment_score or 0.0) < -0.15]
    
    # Severity assessment
    if avg_threat >= 0.70 or len(critical_comments) >= 3:
        overall_threat_level = "CRITICAL"
        threat_color = "#ef4444"
    elif avg_threat >= 0.45 or len(high_comments) + len(critical_comments) >= 4:
        overall_threat_level = "HIGH"
        threat_color = "#f97316"
    elif avg_threat >= 0.25 or len(high_comments) > 0:
        overall_threat_level = "MODERATE"
        threat_color = "#eab308"
    else:
        overall_threat_level = "LOW / SAFE"
        threat_color = "#10b981"
        
    if avg_sentiment > 0.15:
        sentiment_verdict = "Predominantly Positive / Favorable"
    elif avg_sentiment < -0.15:
        sentiment_verdict = "Predominantly Negative / Hostile"
    else:
        sentiment_verdict = "Neutral / Mixed"

    return {
        "video_title": video_title,
        "channel_name": channel_name,
        "video_url": video_post.url,
        "video_id": video_post.post_id,
        "video_views": video_views,
        "video_likes": video_likes,
        "total_comments": total_comments,
        "total_comment_likes": total_comment_likes,
        "max_comment_likes": max_comment_likes,
        "avg_threat": avg_threat,
        "avg_sentiment": avg_sentiment,
        "overall_threat_level": overall_threat_level,
        "threat_color": threat_color,
        "sentiment_verdict": sentiment_verdict,
        "critical_count": len(critical_comments),
        "high_count": len(high_comments),
        "moderate_count": len(moderate_comments),
        "low_count": len(low_comments),
        "critical_comments": critical_comments,
        "high_comments": high_comments,
        "moderate_comments": moderate_comments,
        "low_comments": low_comments,
        "positive_count": len(positive_comments),
        "neutral_count": len(neutral_comments),
        "negative_count": len(negative_comments),
        "label_counts": label_counts,
    }


def generate_single_video_ai_summary(metrics: Dict[str, Any], processed_comments: List[Post]) -> str:
    """
    Generates an automated AI intelligence summary analyzing the video's threat dynamics and audience sentiment.
    """
    total = metrics["total_comments"]
    if total == 0:
        return "No comments were available for this video to produce an AI summary assessment."
    
    crit = metrics["critical_count"]
    high = metrics["high_count"]
    avg_t = metrics["avg_threat"]
    avg_s = metrics["avg_sentiment"]
    labels = metrics["label_counts"]
    top_threat = sorted(labels.items(), key=lambda x: x[1], reverse=True)
    dominant_category = top_threat[0][0].replace("_", " ").title() if top_threat else "Neutral Mention"
    
    hostile_ratio = ((crit + high) / total) * 100
    
    summary_paragraphs = []
    
    # 1. Executive Synthesis
    summary_paragraphs.append(
        f"**Executive Assessment**: Video discourse under channel **'{metrics['channel_name']}'** has been evaluated with an overall threat rating of **{metrics['overall_threat_level']}** (Average Threat Index: **{avg_t:.2f} / 1.00**). "
        f"Across {total} analyzed comments, **{crit + high} comments ({hostile_ratio:.1f}%)** cross high-severity monitoring thresholds, generating a cumulative **{metrics['total_comment_likes']:,} comment likes**."
    )
    
    # 2. Narrative Dynamics & Sentiment Polarity
    if avg_s < -0.20:
        sent_analysis = (
            f"Audience reaction demonstrates acute negative polarity (Average Sentiment: **{avg_s:.2f}**). "
            f"The discourse is dominated by **{metrics['negative_count']} negative comments** versus {metrics['positive_count']} supportive mentions. "
            f"The primary threat vector identified is **{dominant_category}**, indicating active antagonistic framing."
        )
    elif avg_s > 0.20:
        sent_analysis = (
            f"Audience reaction exhibits positive resilience (Average Sentiment: **{avg_s:.2f}**), with {metrics['positive_count']} favorable comments outweighing hostile sentiment. "
            f"Despite isolated critical spikes, general community perception remains predominantly supportive."
        )
    else:
        sent_analysis = (
            f"Audience reaction reflects polarized or neutral discourse (Average Sentiment: **{avg_s:.2f}**). "
            f"Conversations are split between critical evaluations and organic community dialogue, with **{dominant_category}** leading classified thematic tags."
        )
    summary_paragraphs.append(sent_analysis)
    
    # 3. High Risk & Amplification Vectors
    top_liked_critical = sorted(
        [c for c in processed_comments if (c.threat_score or 0.0) >= 0.5],
        key=lambda x: x.engagement.get("likes", 0),
        reverse=True
    )
    if top_liked_critical:
        top_c = top_liked_critical[0]
        summary_paragraphs.append(
            f"**High-Engagement Hostile Node**: The most amplified hostile narrative is authored by **{top_c.author_name}** "
            f"(Likes: **{top_c.engagement.get('likes', 0):,}**, Threat Score: **{top_c.threat_score:.2f}**), "
            f"which poses algorithmic propagation risk if left unaddressed: *\"{top_c.text[:120]}...\"*"
        )
    else:
        summary_paragraphs.append(
            "No single high-threat comment has achieved runaway viral traction in the current sample."
        )
        
    return "\n\n".join(summary_paragraphs)


def generate_single_video_action_steps(metrics: Dict[str, Any], processed_comments: List[Post]) -> List[Dict[str, str]]:
    """
    Generates actionable, structured strategic & tactical steps to be taken based on metrics.
    """
    crit = metrics["critical_count"]
    high = metrics["high_count"]
    avg_t = metrics["avg_threat"]
    labels = metrics["label_counts"]
    
    steps = []
    
    # Category 1: Immediate Takedown & Platform Moderation
    if crit > 0 or labels.get("smear_campaign", 0) > 0 or labels.get("coordinated_attack", 0) > 0:
        steps.append({
            "phase": "Immediate Takedown & Platform Moderation",
            "priority": "HIGH",
            "action": (
                f"Flag and submit YouTube Community Guideline violation reports on {crit + high} identified high-severity comments. "
                f"Target specifically smear campaign and coordinated trolling accounts for abusive language, hate speech, or harassment."
            )
        })
    else:
        steps.append({
            "phase": "Routine Community Moderation",
            "priority": "NORMAL",
            "action": "Maintain standard automated moderation filter for hate speech and spam triggers."
        })
        
    # Category 2: Counter-Narrative & Factual Rebuttal
    if labels.get("misinformation", 0) > 0 or avg_t >= 0.40:
        steps.append({
            "phase": "Counter-Narrative & Fact-Checking",
            "priority": "HIGH",
            "action": (
                "Deploy an official pinned context comment or issue a verified press note/fact-sheet "
                "refuting distorted claims highlighted in the video comment thread with verifiable citations and timestamps."
            )
        })
    else:
        steps.append({
            "phase": "Audience Engagement",
            "priority": "LOW",
            "action": "Amplify constructive dialogue by acknowledging supportive comments and community feedback."
        })
        
    # Category 3: Grassroots Digital Mobilization
    if (crit + high) >= 2 or metrics["avg_sentiment"] < -0.10:
        steps.append({
            "phase": "Digital Cadre Mobilization",
            "priority": "MEDIUM",
            "action": (
                "Alert digital communication teams to engage constructively in the comment section with verified facts, "
                "upvoting accurate rebuttals to counterbalance top algorithmic hostile comments."
            )
        })
        
    # Category 4: Evidentiary Logging & Legal Escalation
    if crit >= 2 or avg_t >= 0.70 or labels.get("smear_campaign", 0) >= 3:
        steps.append({
            "phase": "Legal & Cyber Cell Evidentiary Logging",
            "priority": "HIGH",
            "action": (
                "Archive forensic snapshots (author IDs, comment CIDs, timestamps, permalinks) "
                "for legal evaluation regarding potential defamatory campaign / Section 66A IT Act or Bharatiya Nyaya Sanhita compliance filings."
            )
        })
        
    # Category 5: Surveillance & Monitoring Cadence
    monitoring_interval = "every 3-4 hours" if avg_t >= 0.50 else "every 12-24 hours"
    steps.append({
        "phase": "Monitoring & Early Warning Cadence",
        "priority": "MEDIUM",
        "action": f"Set video URL on active re-scan interval ({monitoring_interval}) to detect virality spikes or cross-platform migration to X/Instagram/Telegram."
    })
    
    return steps


def generate_single_video_markdown_report(video_post: Post, processed_comments: List[Post]) -> str:
    """
    Renders a complete, beautifully structured Markdown report for a single video analysis.
    """
    metrics = compute_single_video_metrics(video_post, processed_comments)
    ai_summary = generate_single_video_ai_summary(metrics, processed_comments)
    action_steps = generate_single_video_action_steps(metrics, processed_comments)
    
    report = io.StringIO()
    
    # 1. Header
    report.write("# 🛡️ SINGLE VIDEO THREAT INTELLIGENCE & SENTIMENT REPORT\n")
    report.write(f"**Generated**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Local Time)  \n")
    report.write(f"**Target Entity**: Naam Tamilar Katchi (NTK) / Social Threat Intelligence Pipeline  \n")
    report.write(f"**Source Platform**: YouTube  \n\n")
    report.write("---\n\n")
    
    # 2. Target Video Metadata
    report.write("## 1. Video Profile & Scope\n\n")
    report.write(f"- **Video Title**: {metrics['video_title']}\n")
    report.write(f"- **Channel / Author**: {metrics['channel_name']}\n")
    report.write(f"- **Video URL**: [{metrics['video_url']}]({metrics['video_url']})\n")
    report.write(f"- **Video ID**: `{metrics['video_id']}`\n")
    views_str = f"{metrics['video_views']:,}" if metrics['video_views'] > 0 else "N/A"
    likes_str = f"{metrics['video_likes']:,}" if metrics['video_likes'] > 0 else "N/A"
    report.write(f"- **Video Views**: {views_str}\n")
    report.write(f"- **Video Likes**: {likes_str}\n")
    report.write(f"- **Comments Sampled & Analyzed**: {metrics['total_comments']}\n")
    report.write(f"- **Total Comment Likes (Engagement)**: {metrics['total_comment_likes']:,}\n\n")
    
    # 3. Key Metrics Table
    report.write("## 2. Threat & Sentiment Metric Summary\n\n")
    report.write("| Metric | Value | Reference / Range |\n")
    report.write("| :--- | :--- | :--- |\n")
    report.write(f"| **Overall Threat Level** | **{metrics['overall_threat_level']}** | Low / Moderate / High / Critical |\n")
    report.write(f"| **Average Threat Index** | **{metrics['avg_threat']:.2f}** | 0.00 (Safe) to 1.00 (Severe) |\n")
    report.write(f"| **Average Sentiment Score** | **{metrics['avg_sentiment']:.2f}** | -1.00 (Hostile) to +1.00 (Supportive) |\n")
    report.write(f"| **Sentiment Outlook** | {metrics['sentiment_verdict']} | Polarity Assessment |\n")
    report.write(f"| **Critical Threats (Score ≥ 0.80)** | {metrics['critical_count']} | High Priority Intervention |\n")
    report.write(f"| **High Threats (Score 0.50 - 0.79)** | {metrics['high_count']} | Active Monitoring |\n")
    report.write(f"| **Moderate Threats (0.30 - 0.49)** | {metrics['moderate_count']} | Contextual Dialogue |\n")
    report.write(f"| **Low / Neutral Mentions (< 0.30)** | {metrics['low_count']} | Safe / Organic |\n")
    report.write(f"| **Total Likes on Scraped Comments** | {metrics['total_comment_likes']:,} | Audience Endorsement Volume |\n\n")
    
    # 4. Threat Category Distribution
    report.write("### Threat Category Breakdown\n\n")
    report.write("| Category | Count | Percentage |\n")
    report.write("| :--- | :---: | :---: |\n")
    for lbl, cnt in sorted(metrics["label_counts"].items(), key=lambda x: x[1], reverse=True):
        pct = (cnt / metrics['total_comments'] * 100) if metrics['total_comments'] > 0 else 0
        report.write(f"| {lbl.replace('_', ' ').title()} | {cnt} | {pct:.1f}% |\n")
    report.write("\n")
    
    # 5. AI Executive Summary
    report.write("## 3. AI Threat & Sentiment Intelligence Assessment\n\n")
    report.write(f"{ai_summary}\n\n")
    
    # 6. Actionable Suggestions & Steps to be Taken
    report.write("## 4. Recommended Actions & Steps to be Taken\n\n")
    for idx, s in enumerate(action_steps, 1):
        report.write(f"### 4.{idx} [{s['priority']} PRIORITY] {s['phase']}\n")
        report.write(f"- **Action Plan**: {s['action']}\n\n")
        
    # 7. High-Risk Flagged Comments Detailed Audit
    report.write("## 5. Detailed High-Risk Comments Audit\n\n")
    sorted_threat_comments = sorted(
        processed_comments, 
        key=lambda x: (x.threat_score or 0.0, x.engagement.get("likes", 0)), 
        reverse=True
    )
    flagged = [c for c in sorted_threat_comments if (c.threat_score or 0.0) >= 0.50]
    
    if flagged:
        for idx, c in enumerate(flagged, 1):
            sev = "CRITICAL" if (c.threat_score or 0.0) >= 0.80 else "HIGH"
            report.write(f"#### #{idx} [{sev}] Author: `{c.author_name}`\n")
            report.write(f"- **Threat Score**: `{c.threat_score:.2f}` | **Threat Label**: `{c.threat_label.replace('_', ' ').title()}`\n")
            report.write(f"- **Sentiment Score**: `{c.sentiment_score:.2f}` | **Comment Likes**: `{c.engagement.get('likes', 0):,}`\n")
            report.write(f"- **Comment Link**: [{c.url}]({c.url})\n")
            clean_text = c.text.replace("\n", " ")
            report.write(f"- **Content Snippet**:\n  > {clean_text}\n\n")
    else:
        report.write("No high or critical severity comments detected in the analyzed sample.\n\n")
        
    # 8. Top Engaged Comments (Community Pulse)
    report.write("## 6. Top Engaged Comments (Community Pulse)\n\n")
    sorted_by_likes = sorted(processed_comments, key=lambda x: x.engagement.get("likes", 0), reverse=True)[:5]
    if sorted_by_likes and sorted_by_likes[0].engagement.get("likes", 0) > 0:
        for idx, c in enumerate(sorted_by_likes, 1):
            report.write(f"**{idx}. `{c.author_name}` ({c.engagement.get('likes', 0):,} likes | Threat: {c.threat_score:.2f})**\n")
            report.write(f"> {c.text.replace(chr(10), ' ')}\n\n")
    else:
        report.write("No comment like velocity recorded.\n\n")
        
    report.write("---\n")
    report.write("*End of Single Video Intelligence Report. Generated via NTK Threat Monitor Pipeline.*")
    
    return report.getvalue()
