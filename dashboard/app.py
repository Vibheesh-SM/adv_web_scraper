import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
from typing import Tuple, List
from sqlalchemy import desc

# Add project root to path so we can import modules
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import importlib
import database.database
importlib.reload(database.database)

from database.database import SessionLocal, DBPost, init_db, purge_expired_records, DBHostileChannel
import collectors.youtube
import collectors.twitter
import collectors.facebook
import collectors.google_news
import collectors.reddit
import collectors.mastodon
import collectors.telegram
import collectors.main_media
import collectors.instagram
import pipeline.classify
import pipeline.pre_filter
import alerts.alerts

importlib.reload(collectors.youtube)
importlib.reload(collectors.twitter)
importlib.reload(collectors.facebook)
importlib.reload(collectors.google_news)
importlib.reload(collectors.reddit)
importlib.reload(collectors.mastodon)
importlib.reload(collectors.telegram)
importlib.reload(collectors.main_media)
importlib.reload(collectors.instagram)
importlib.reload(pipeline.classify)
importlib.reload(pipeline.pre_filter)
importlib.reload(alerts.alerts)

from collectors.youtube import fetch_youtube_threats
from collectors.twitter import fetch_twitter_threats
from collectors.facebook import fetch_facebook_threats
from collectors.google_news import fetch_google_news_threats
from collectors.reddit import fetch_reddit_threats
from collectors.mastodon import fetch_mastodon_threats
from collectors.telegram import fetch_telegram_threats
from collectors.main_media import fetch_main_media_threats
from collectors.instagram import fetch_instagram_threats
from pipeline.classify import classify_and_score
from pipeline.pre_filter import should_process_post
from alerts.alerts import dispatch_alert
from pipeline.single_video_report import (
    compute_single_video_metrics,
    generate_single_video_ai_summary,
    generate_single_video_action_steps,
    generate_single_video_markdown_report
)

import urllib.parse

# Initialize database
init_db()

# Set page config
st.set_page_config(
    page_title="NTK Party Social Media Threat Monitor",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (Dark Mode, Solid colors)
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
        color: #ffffff;
    }
    .metric-card {
        background-color: #1f2937;
        border: 1px solid #374151;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 20px;
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: bold;
        color: #3b82f6;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }
</style>
""", unsafe_allow_html=True)

def render_single_video_analysis(video_post, processed_comments, is_standalone=False):
    """
    Renders the Single Video Analyzer dashboard view, complete with 8 metric cards,
    dedicated Markdown / CSV exporter, AI Threat Assessment summary, action steps,
    and a searchable/sortable analyzed comments feed.
    """
    metrics = compute_single_video_metrics(video_post, processed_comments)
    report_markdown = generate_single_video_markdown_report(video_post, processed_comments)
    ai_summary = generate_single_video_ai_summary(metrics, processed_comments)
    action_steps = generate_single_video_action_steps(metrics, processed_comments)
    
    st.markdown("---")
    
    # Video Title & Header Card
    st.markdown(f"### 📹 {metrics['video_title']}")
    st.markdown(f"**Channel**: `{metrics['channel_name']}` &nbsp;|&nbsp; **URL**: [{metrics['video_url']}]({metrics['video_url']}) &nbsp;|&nbsp; **Video ID**: `{metrics['video_id']}`")
    
    # 8-Card Quantitative Metric Grid
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="metric-card" style="background-color: #1f2937; border: 1px solid #374151; padding: 18px; border-radius: 10px; text-align: center;">
            <div style="font-size: 1.8rem; font-weight: bold; color: #3b82f6;">{metrics['video_views']:,}</div>
            <div style="font-size: 0.85rem; color: #9ca3af; text-transform: uppercase;">Video Views</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        likes_display = f"{metrics['video_likes']:,}" if metrics['video_likes'] > 0 else "N/A"
        st.markdown(f"""
        <div class="metric-card" style="background-color: #1f2937; border: 1px solid #374151; padding: 18px; border-radius: 10px; text-align: center;">
            <div style="font-size: 1.8rem; font-weight: bold; color: #3b82f6;">{likes_display}</div>
            <div style="font-size: 0.85rem; color: #9ca3af; text-transform: uppercase;">Video Likes</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card" style="background-color: #1f2937; border: 1px solid #374151; padding: 18px; border-radius: 10px; text-align: center;">
            <div style="font-size: 1.8rem; font-weight: bold; color: #10b981;">{metrics['total_comments']}</div>
            <div style="font-size: 0.85rem; color: #9ca3af; text-transform: uppercase;">Comments Sampled</div>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="metric-card" style="background-color: #1f2937; border: 1px solid #374151; padding: 18px; border-radius: 10px; text-align: center;">
            <div style="font-size: 1.8rem; font-weight: bold; color: #ec4899;">{metrics['total_comment_likes']:,}</div>
            <div style="font-size: 0.85rem; color: #9ca3af; text-transform: uppercase;">Total Comment Likes</div>
        </div>
        """, unsafe_allow_html=True)

    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.markdown(f"""
        <div class="metric-card" style="background-color: #1f2937; border: 1px solid #374151; padding: 18px; border-radius: 10px; text-align: center;">
            <div style="font-size: 1.8rem; font-weight: bold; color: {metrics['threat_color']};">{metrics['avg_threat']:.2f} <span style="font-size: 0.85rem;">({metrics['overall_threat_level']})</span></div>
            <div style="font-size: 0.85rem; color: #9ca3af; text-transform: uppercase;">Avg Threat Index</div>
        </div>
        """, unsafe_allow_html=True)
    with c6:
        sent_color = '#ef4444' if metrics['avg_sentiment'] < -0.15 else ('#10b981' if metrics['avg_sentiment'] > 0.15 else '#9ca3af')
        st.markdown(f"""
        <div class="metric-card" style="background-color: #1f2937; border: 1px solid #374151; padding: 18px; border-radius: 10px; text-align: center;">
            <div style="font-size: 1.8rem; font-weight: bold; color: {sent_color};">{metrics['avg_sentiment']:.2f}</div>
            <div style="font-size: 0.85rem; color: #9ca3af; text-transform: uppercase;">Avg Sentiment</div>
        </div>
        """, unsafe_allow_html=True)
    with c7:
        flagged_total = metrics['critical_count'] + metrics['high_count']
        st.markdown(f"""
        <div class="metric-card" style="background-color: #1f2937; border: 1px solid #374151; padding: 18px; border-radius: 10px; text-align: center;">
            <div style="font-size: 1.8rem; font-weight: bold; color: {'#ef4444' if flagged_total > 0 else '#10b981'};">{flagged_total}</div>
            <div style="font-size: 0.85rem; color: #9ca3af; text-transform: uppercase;">Critical / High Alerts</div>
        </div>
        """, unsafe_allow_html=True)
    with c8:
        st.markdown(f"""
        <div class="metric-card" style="background-color: #1f2937; border: 1px solid #374151; padding: 18px; border-radius: 10px; text-align: center;">
            <div style="font-size: 1.8rem; font-weight: bold; color: #8b5cf6;">{metrics['max_comment_likes']:,}</div>
            <div style="font-size: 0.85rem; color: #9ca3af; text-transform: uppercase;">Max Comment Likes</div>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("---")
    
    # 📥 DEDICATED MARKDOWN & DATA EXPORTER SECTION
    st.markdown("### 📥 Single Video Threat Intelligence Exporter")
    st.markdown("Download an intelligence assessment dossier (Markdown) containing all quantitative metrics, AI narrative synthesis, high-risk flagged comments, and strategic next steps.")
    
    exp_col1, exp_col2 = st.columns([1, 1])
    filename_ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    with exp_col1:
        st.markdown("#### Export Assessment Dossier")
        st.download_button(
            label="📄 Download Video Intelligence Report (Markdown)",
            data=report_markdown,
            file_name=f"single_video_threat_report_{metrics['video_id']}_{filename_ts}.md",
            mime="text/markdown",
            use_container_width=True
        )
        
        # CSV Export for comments
        comm_records = []
        for c in processed_comments:
            comm_records.append({
                "author": c.author_name,
                "text": c.text,
                "threat_score": c.threat_score,
                "threat_label": c.threat_label,
                "sentiment_score": c.sentiment_score,
                "likes": c.engagement.get("likes", 0),
                "url": c.url,
                "published_at": c.published_at.strftime("%Y-%m-%d %H:%M:%S") if c.published_at else ""
            })
        if comm_records:
            comm_df = pd.DataFrame(comm_records)
            st.download_button(
                label="📊 Export Analyzed Comments (CSV)",
                data=comm_df.to_csv(index=False).encode('utf-8'),
                file_name=f"single_video_comments_{metrics['video_id']}_{filename_ts}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
    with exp_col2:
        st.markdown("#### Assessment Dossier Highlights")
        st.markdown(f"""
        <div style="background-color: #111827; border: 1px solid #374151; padding: 14px 18px; border-radius: 8px;">
            <div style="color: #9ca3af; font-size: 0.8rem; text-transform: uppercase; font-weight: 600; margin-bottom: 6px;">Report Dossier Contents</div>
            <div style="color: #e5e7eb; font-size: 0.9rem; line-height: 1.6;">
                • <strong>Overall Verdict</strong>: <span style="color: {metrics['threat_color']}; font-weight: bold;">{metrics['overall_threat_level']} Threat Index ({metrics['avg_threat']:.2f})</span><br/>
                • <strong>Public Sentiment</strong>: {metrics['sentiment_verdict']} ({metrics['avg_sentiment']:.2f})<br/>
                • <strong>Total Audience Engagement</strong>: {metrics['total_comment_likes']:,} likes across {metrics['total_comments']} comments<br/>
                • <strong>Includes</strong>: Full AI narrative analysis, detailed flagged comment quotes & links, and a 5-point strategic response plan.
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with st.expander("📄 View Live Markdown Report Content Preview", expanded=False):
        st.text_area("Live Markdown Report Preview", value=report_markdown, height=350, disabled=True)
        
    st.markdown("---")
    
    # 🤖 AI SYNTHESIS & 🎯 STEPS TO BE TAKEN
    col_ai, col_steps = st.columns(2)
    with col_ai:
        st.markdown("### 🤖 AI Threat & Sentiment Intelligence Assessment")
        st.markdown(f"""
        <div style="background-color: #1f2937; border: 1px solid #374151; border-left: 4px solid {metrics['threat_color']}; padding: 18px; border-radius: 8px; line-height: 1.6; color: #e5e7eb; font-size: 0.95rem;">
            {ai_summary.replace(chr(10)+chr(10), '<br/><br/>')}
        </div>
        """, unsafe_allow_html=True)
        
    with col_steps:
        st.markdown("### 🎯 Recommended Strategic & Tactical Steps")
        for step in action_steps:
            p_color = "#ef4444" if step["priority"] == "HIGH" else ("#f59e0b" if step["priority"] == "MEDIUM" else "#10b981")
            st.markdown(f"""
            <div style="background-color: #1f2937; border: 1px solid #374151; border-left: 4px solid {p_color}; padding: 12px 16px; border-radius: 8px; margin-bottom: 10px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <strong style="color: #f3f4f6; font-size: 0.95rem;">{step['phase']}</strong>
                    <span style="background-color: {p_color}22; color: {p_color}; border: 1px solid {p_color}; padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: bold;">{step['priority']} PRIORITY</span>
                </div>
                <div style="color: #d1d5db; font-size: 0.88rem; line-height: 1.4;">{step['action']}</div>
            </div>
            """, unsafe_allow_html=True)
            
    st.markdown("---")
    
    # 💬 ANALYZED COMMENTS FEED
    st.markdown(f"### 💬 Analyzed Video Comments ({metrics['total_comments']})")
    
    fcol1, fcol2 = st.columns([2, 2])
    with fcol1:
        filter_opt = st.selectbox(
            "Filter Comments Feed",
            ["All Analyzed Comments", "Critical Threats (≥ 0.80)", "High & Critical Threats (≥ 0.50)", "Negative Sentiment (< -0.15)", "Positive Mentions (> +0.15)"],
            key=f"sv_filter_{metrics['video_id']}_{'standalone' if is_standalone else 'tab'}"
        )
    with fcol2:
        sort_opt = st.selectbox(
            "Sort Order",
            ["Highest Threat Score First", "Most Liked Comments First", "Most Negative Sentiment First"],
            key=f"sv_sort_{metrics['video_id']}_{'standalone' if is_standalone else 'tab'}"
        )
        
    filtered_list = list(processed_comments)
    if filter_opt == "Critical Threats (≥ 0.80)":
        filtered_list = [c for c in filtered_list if (c.threat_score or 0.0) >= 0.80]
    elif filter_opt == "High & Critical Threats (≥ 0.50)":
        filtered_list = [c for c in filtered_list if (c.threat_score or 0.0) >= 0.50]
    elif filter_opt == "Negative Sentiment (< -0.15)":
        filtered_list = [c for c in filtered_list if (c.sentiment_score or 0.0) < -0.15]
    elif filter_opt == "Positive Mentions (> +0.15)":
        filtered_list = [c for c in filtered_list if (c.sentiment_score or 0.0) > 0.15]
        
    if sort_opt == "Highest Threat Score First":
        filtered_list.sort(key=lambda x: x.threat_score or 0.0, reverse=True)
    elif sort_opt == "Most Liked Comments First":
        filtered_list.sort(key=lambda x: x.engagement.get("likes", 0), reverse=True)
    elif sort_opt == "Most Negative Sentiment First":
        filtered_list.sort(key=lambda x: x.sentiment_score or 0.0)
        
    if not filtered_list:
        st.info("No comments match the selected filter criteria.")
    else:
        for c in filtered_list:
            badge_color = "#ef4444" if (c.threat_score or 0.0) >= 0.8 else ("#f59e0b" if (c.threat_score or 0.0) >= 0.5 else "#10b981")
            badge_text = "CRITICAL" if (c.threat_score or 0.0) >= 0.8 else ("HIGH" if (c.threat_score or 0.0) >= 0.5 else "LOW")
            lbl_text = (c.threat_label or "neutral_mention").replace("_", " ").upper()
            
            st.markdown(f"""
            <div style="background-color: #1f2937; padding: 14px; border-radius: 8px; margin-bottom: 12px; border-left: 4px solid {badge_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <strong style="color: #f3f4f6;">{c.author_name}</strong>
                        <span style="background-color: #374151; color: #9ca3af; padding: 1px 6px; border-radius: 4px; font-size: 0.75rem;">{lbl_text}</span>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <span style="background-color: {badge_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: bold;">{badge_text} ({c.threat_score:.2f})</span>
                        <span style="font-size: 0.8rem; color: #9ca3af;">Sent: <strong>{c.sentiment_score:.2f}</strong></span>
                        <span style="font-size: 0.8rem; color: #ec4899;">❤️ <strong>{c.engagement.get('likes', 0):,}</strong></span>
                    </div>
                </div>
                <div style="color: #e5e7eb; font-size: 0.95rem; line-height: 1.4; margin-top: 4px;">{c.text}</div>
                <div style="margin-top: 8px; text-align: right;">
                    <a href="{c.url}" target="_blank" style="color: #60a5fa; font-size: 0.78rem; text-decoration: none;">View on YouTube ↗</a>
                </div>
            </div>
            """, unsafe_allow_html=True)


# Check if we should render standalone video analyzer "new page"
analyze_param = st.query_params.get("analyze", None)
if analyze_param:
    st.markdown("### 🎯 Single Video Threat & Sentiment Deep Dive")
    st.markdown(f"**Target URL:** `{analyze_param}`")
    if st.button("← Back to Dashboard"):
        st.query_params.clear()
        st.rerun()
        
    with st.spinner("Scraping video data and fetching audience comments..."):
        try:
            from collectors.youtube import fetch_single_video_data
            from pipeline.classify import classify_and_score
            
            data = fetch_single_video_data(analyze_param, max_comments=40)
            video_post = data["video"]
            raw_comments = data["comments"]
            
            processed_comments = []
            for comment in raw_comments:
                processed_comments.append(classify_and_score(comment))
                
            render_single_video_analysis(video_post, processed_comments, is_standalone=True)
                
        except Exception as e:
            st.error(f"Failed to analyze video: {str(e)}")
            
    st.stop()

# Helper function to load data from database
def load_data():
    session = SessionLocal()
    try:
        state = get_global_scheduler_state()
        max_age_days = state.get("max_post_age_days", 3)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
        cutoff_naive = cutoff.replace(tzinfo=None)
        
        # Load only posts within the max_post_age_days timeframe directly from the database
        query = session.query(DBPost).filter(DBPost.published_at >= cutoff_naive).order_by(desc(DBPost.published_at)).all()
        data = []
        for post in query:
            data.append({
                "post_id": post.post_id,
                "platform": post.platform,
                "text": post.text,
                "author_name": post.author_name,
                "published_at": post.published_at,
                "threat_score": post.threat_score,
                "threat_label": post.threat_label,
                "sentiment_score": post.sentiment_score,
                "flagged": post.flagged,
                "url": post.url
            })
        if not data:
            return pd.DataFrame(columns=["post_id", "platform", "text", "author_name", "published_at", "threat_score", "threat_label", "sentiment_score", "flagged", "url"])
        return pd.DataFrame(data)
    finally:
        session.close()

# Interactive Network Visualizer using Pyvis & NetworkX
def render_network_graph(df):
    if df.empty:
        return ""
    
    import networkx as nx
    from pyvis.network import Network
    import tempfile
    
    # Initialize Pyvis Network with dark theme matching dashboard aesthetics
    net = Network(height="500px", width="100%", bgcolor="#0e1117", font_color="#ffffff")
    
    G = nx.Graph()
    
    # Platform color mapping (harmonic tones matching dashboard style)
    platform_colors = {
        "twitter": "#1da1f2",
        "youtube": "#ff0000",
        "facebook": "#1877f2"
    }
    
    # Get keywords to search for connections
    target_kws = [kw.strip().lower() for kw in os.getenv("TARGET_KEYWORDS", "organization_name").split(",")]
    
    # Track which keywords and categories actually appear in data to avoid cluttered empty nodes
    active_keywords = set()
    active_categories = set()
    
    # Pre-scan to find active nodes
    for _, row in df.iterrows():
        text_lower = row['text'].lower()
        active_categories.add(row['threat_label'])
        for kw in target_kws:
            if kw in text_lower:
                active_keywords.add(kw)
                
    # Add Keyword hub nodes (gold diamonds)
    for kw in active_keywords:
        G.add_node(
            f"kw_{kw}",
            label=f"Target: {kw.upper()}",
            color="#f59e0b",
            shape="diamond",
            size=25,
            title=f"Target Keyword: {kw}"
        )
        
    # Add Threat Label hub nodes (purple stars)
    for label in active_categories:
        G.add_node(
            f"cat_{label}",
            label=f"Threat: {label.upper()}",
            color="#a78bfa",
            shape="star",
            size=22,
            title=f"Threat Category: {label}"
        )
        
    # Add Author nodes and link them
    for _, row in df.iterrows():
        author = row['author_name']
        platform = row['platform']
        score = row['threat_score']
        label = row['threat_label']
        text_lower = row['text'].lower()
        
        # Determine node border color based on threat severity
        if score >= 0.8:
            border_color = "#ef4444" # Critical/Red
        elif score >= 0.5:
            border_color = "#f59e0b" # High/Orange
        else:
            border_color = "#10b981" # Low/Green
            
        author_node_id = f"auth_{author}_{platform}"
        bg_color = platform_colors.get(platform, "#6b7280")
        
        # Scale node size based on threat score to show impact weight
        node_size = 14 + int(score * 20)
        
        G.add_node(
            author_node_id,
            label=author,
            color={
                "background": bg_color,
                "border": border_color,
                "highlight": {"background": "#ffffff", "border": "#3b82f6"}
            },
            shape="dot",
            size=node_size,
            title=f"Platform: {platform.upper()}<br>Threat Score: {score:.2f}<br>Category: {label}"
        )
        
        # Edge to threat category
        G.add_edge(author_node_id, f"cat_{label}", color="#4b5563", width=1.5, dashes=True)
        
        # Edges to matched keywords
        for kw in active_keywords:
            if kw in text_lower:
                G.add_edge(author_node_id, f"kw_{kw}", color="#9ca3af", width=2.0)
                
    # Load into Pyvis Network
    net.from_nx(G)
    
    # Configure graph physics options for smooth micro-animations and layout spacing
    net.set_options("""
    var options = {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -55,
          "centralGravity": 0.015,
          "springLength": 110,
          "springStrength": 0.08
        },
        "maxVelocity": 50,
        "solver": "forceAtlas2Based",
        "timestep": 0.35,
        "stabilization": {"iterations": 150}
      },
      "edges": {
        "smooth": {
          "type": "continuous",
          "forceDirection": "none"
        }
      }
    }
    """)
    
    # Generate HTML content using temporary file wrapper safely
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
        net.save_graph(tmp.name)
        tmp_path = tmp.name
        
    with open(tmp_path, "r", encoding="utf-8") as f:
        html_code = f.read()
        
    try:
        os.remove(tmp_path)
    except:
        pass
        
    return html_code

import threading
import time
import datetime

import os

@st.cache_resource
def get_session_run_id():
    import uuid
    return uuid.uuid4().hex

CURRENT_RUN_ID = get_session_run_id()

@st.cache_resource
def get_global_scheduler_state():
    return {
        "status": "Inactive",
        "last_ingestion": None,
        "next_ingestion": None,
        "last_scan": None,
        "next_scan": None,
        "enabled": True,
        "ingestion_interval_minutes": 30,
        "scan_interval_minutes": 10,
        "active_run_id": None,
        "running_run_id": None,
        "max_post_age_days": 3
    }

scheduler_state = get_global_scheduler_state()
ingestion_lock = threading.Lock()

def run_ingestion_only(custom_keywords: List[str] = None, strict_hashtag_mode: bool = False) -> int:
    # Prevent concurrent execution issues using a non-blocking lock acquire
    acquired = ingestion_lock.acquire(blocking=False)
    if not acquired:
        raise RuntimeError("Ingestion is already in progress in another thread.")
        
    try:
        # Fetch posts concurrently across all platform collectors
        from concurrent.futures import ThreadPoolExecutor
        
        collector_funcs = [
            fetch_youtube_threats,
            fetch_twitter_threats,
            fetch_facebook_threats,
            fetch_google_news_threats,
            fetch_reddit_threats,
            fetch_mastodon_threats,
            fetch_telegram_threats,
            fetch_main_media_threats,
            fetch_instagram_threats
        ]
        
        raw_posts = []
        with ThreadPoolExecutor(max_workers=len(collector_funcs)) as executor:
            futures = [executor.submit(func, custom_keywords=custom_keywords) for func in collector_funcs]
            for future in futures:
                try:
                    res = future.result()
                    if res:
                        raw_posts.extend(res)
                except Exception as ce:
                    print(f"[Ingestion Engine] Collector execution failed: {ce}")
        
        # Strict custom hashtag mode filter prior to saving to DB
        if custom_keywords and strict_hashtag_mode:
            cleaned_kws = [k.strip().lower().lstrip("#") for k in custom_keywords if k.strip()]
            if cleaned_kws:
                raw_posts = [
                    p for p in raw_posts 
                    if any(k in p.text.lower() for k in cleaned_kws)
                ]

        # Deduplicate raw_posts by post_id
        seen_ids = set()
        deduped_posts = []
        for post in raw_posts:
            if post.post_id not in seen_ids:
                seen_ids.add(post.post_id)
                deduped_posts.append(post)
        raw_posts = deduped_posts
        
        session = SessionLocal()
        new_records = 0
        
        max_age_days = scheduler_state.get("max_post_age_days", 3)
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
        
        try:
            for rp in raw_posts:
                # Filter out posts older than the sliding day window
                pub_at = rp.published_at
                if pub_at.tzinfo is None:
                    pub_at = pub_at.replace(tzinfo=datetime.timezone.utc)
                if pub_at < cutoff_date:
                    continue
                    
                # Verify political context relevance to ignore noise/false positives
                should_c, _ = should_process_post(rp, custom_keywords=custom_keywords)
                if not should_c:
                    continue
                    
                # Check if already in DB to avoid double alert
                existing = session.query(DBPost).filter(DBPost.post_id == rp.post_id).first()
                if not existing:
                    # Save with pending label and default threat score
                    db_p = DBPost(
                        post_id=rp.post_id,
                        platform=rp.platform,
                        text=rp.text,
                        author_id=rp.author_id,
                        author_name=rp.author_name,
                        published_at=rp.published_at,
                        url=rp.url,
                        threat_score=0.0,
                        threat_label="pending",
                        sentiment_score=0.0,
                        flagged=False,
                        processed_at=datetime.datetime.now(datetime.timezone.utc),
                        engagement=rp.engagement
                    )
                    session.add(db_p)
                    new_records += 1
            session.commit()
            purge_expired_records(retention_days=max_age_days)
            return new_records
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    finally:
        ingestion_lock.release()

def run_scan_only() -> Tuple[int, int]:
    session = SessionLocal()
    scanned_count = 0
    flagged_count = 0
    scheduler_state["scan_active"] = True
    try:
        pending_posts = session.query(DBPost).filter(DBPost.threat_label == "pending").all()
        for db_p in pending_posts:
            # Reconstruct post for classification
            from pipeline.schema import Post as SchemaPost
            post_obj = SchemaPost(
                post_id=db_p.post_id,
                platform=db_p.platform,
                text=db_p.text,
                author_id=db_p.author_id,
                author_name=db_p.author_name,
                published_at=db_p.published_at,
                url=db_p.url,
                engagement=db_p.engagement
            )
            
            scored = classify_and_score(post_obj)
            db_p.threat_score = scored.threat_score
            db_p.threat_label = scored.threat_label
            db_p.sentiment_score = scored.sentiment_score
            db_p.flagged = scored.flagged
            db_p.processed_at = scored.processed_at
            
            scanned_count += 1
            if scored.flagged:
                flagged_count += 1
                dispatch_alert(scored)
                from database.database import update_hostile_channel
                update_hostile_channel(
                    author_id=db_p.author_id,
                    author_name=db_p.author_name,
                    platform=db_p.platform,
                    threat_score=db_p.threat_score
                )
                
        session.commit()
        max_age_days = scheduler_state.get("max_post_age_days", 3)
        purge_expired_records(retention_days=max_age_days)
        return scanned_count, flagged_count
    except Exception as e:
        session.rollback()
        raise e
    finally:
        scheduler_state["scan_active"] = False
        session.close()

def rescan_stored_data() -> int:
    session = SessionLocal()
    try:
        posts = session.query(DBPost).all()
        for p in posts:
            p.threat_label = "pending"
        session.commit()
        scanned, flagged = run_scan_only()
        return scanned
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

# Ingestion runner (manual UI trigger)
def run_ingestion(custom_keywords: List[str] = None, strict_hashtag_mode: bool = False):
    kw_desc = f" for custom terms ({', '.join(custom_keywords)})" if custom_keywords else ""
    st.info(f"Triggering ingestion and scanning cycle{kw_desc}...")
    try:
        new_records = run_ingestion_only(custom_keywords=custom_keywords, strict_hashtag_mode=strict_hashtag_mode)
        st.info(f"Ingested {new_records} new posts (status: pending). Running scan...")
        scanned, flagged = run_scan_only()
        st.success(f"Ingestion and scanning complete! Added {new_records} new records ({flagged} flagged as high threat).")
    except RuntimeError as re:
        st.warning(str(re))
    except Exception as e:
        st.error(f"Execution failed: {e}")

# Local background scheduler daemon
def start_background_scheduler():
    # If the thread for the current run is already executing, return
    if scheduler_state.get("running_run_id") == CURRENT_RUN_ID:
        return
        
    # Mark this run as active to terminate stale background threads
    scheduler_state["active_run_id"] = CURRENT_RUN_ID
            
    def loop(thread_run_id):
        # Register this thread as the active running one
        scheduler_state["running_run_id"] = thread_run_id
        
        # Short sleep on startup to let Streamlit server bind and launch
        time.sleep(10)
        print(f"[Scheduler] Background threat monitoring daemon started for run: {thread_run_id}")
        
        last_ingestion = None
        last_scan = None
        
        while True:
            # Check if this thread has been orphaned by a reload
            if scheduler_state.get("active_run_id") != thread_run_id:
                print(f"[Scheduler] Stale background thread {thread_run_id} detected. Exiting thread.")
                break
                
            now = datetime.datetime.now()
            
            # Check Ingestion Timing
            ingest_enabled = scheduler_state.get("enabled", True)
            ingest_interval = scheduler_state.get("ingestion_interval_minutes", 30) * 60
            
            should_ingest = False
            if ingest_enabled:
                if last_ingestion is None or (now - last_ingestion).total_seconds() >= ingest_interval:
                    should_ingest = True
                    
            if should_ingest:
                try:
                    scheduler_state["status"] = "Ingesting"
                    print("[Scheduler] Running automatic background ingestion...")
                    added = run_ingestion_only()
                    print(f"[Scheduler] Ingestion finished. Added {added} pending posts.")
                    last_ingestion = datetime.datetime.now()
                    scheduler_state["last_ingestion"] = last_ingestion
                except RuntimeError:
                    print("[Scheduler] Ingestion locked. Skipping this cycle.")
                except Exception as e:
                    print(f"[Scheduler] Background ingestion failed: {e}")
                    scheduler_state["status"] = "Error"
                    
            # Check Scan Timing
            scan_enabled = scheduler_state.get("enabled", True)
            scan_interval = scheduler_state.get("scan_interval_minutes", 10) * 60
            
            should_scan = False
            if scan_enabled:
                if last_scan is None or (now - last_scan).total_seconds() >= scan_interval:
                    should_scan = True
                    
            if should_scan:
                try:
                    scheduler_state["status"] = "Scanning"
                    print("[Scheduler] Running automatic background threat classification scan...")
                    scanned, flagged = run_scan_only()
                    print(f"[Scheduler] Scan complete. Processed {scanned} pending posts ({flagged} flagged).")
                    last_scan = datetime.datetime.now()
                    scheduler_state["last_scan"] = last_scan
                except Exception as e:
                    print(f"[Scheduler] Background scan failed: {e}")
                    scheduler_state["status"] = "Error"
            
            # Update status
            if not scheduler_state.get("enabled", True):
                scheduler_state["status"] = "Disabled"
                scheduler_state["next_ingestion"] = None
                scheduler_state["next_scan"] = None
            else:
                if scheduler_state["status"] not in ("Ingesting", "Scanning", "Error"):
                    scheduler_state["status"] = "Active"
                    
                if last_ingestion:
                    scheduler_state["next_ingestion"] = last_ingestion + datetime.timedelta(seconds=ingest_interval)
                else:
                    if not scheduler_state.get("next_ingestion"):
                        scheduler_state["next_ingestion"] = datetime.datetime.now() + datetime.timedelta(seconds=ingest_interval)
                
                if last_scan:
                    scheduler_state["next_scan"] = last_scan + datetime.timedelta(seconds=scan_interval)
                else:
                    if not scheduler_state.get("next_scan"):
                        scheduler_state["next_scan"] = datetime.datetime.now() + datetime.timedelta(seconds=scan_interval)
                    
            # Tick sleep (sleep 5 seconds to remain highly responsive to UI state changes)
            time.sleep(5)
            
    thread = threading.Thread(target=loop, args=(CURRENT_RUN_ID,), name="BackgroundIngestionThread", daemon=True)
    thread.start()

# Launch background monitoring loop
start_background_scheduler()

# SIDEBAR STATUS WIDGET
st.sidebar.markdown("### Background Service Status")

if st.sidebar.button("🔄 Refresh Dashboard Data", use_container_width=True):
    st.rerun()

status_val = scheduler_state["status"]
if status_val == "Ingesting":
    status_bg = "#f59e0b"  # amber
    status_label = "Ingesting Data..."
elif status_val == "Scanning":
    status_bg = "#3b82f6"  # blue
    status_label = "Running Threat Scan..."
elif status_val == "Active":
    status_bg = "#10b981"  # emerald green
    status_label = "Active (Idle)"
elif status_val == "Disabled":
    status_bg = "#6b7280"  # gray
    status_label = "Disabled"
elif status_val == "Error":
    status_bg = "#ef4444"  # red
    status_label = "Error"
else:
    status_bg = "#6b7280"  # gray
    status_label = "Inactive"

st.sidebar.markdown(f"""
<div style="border: 1px solid #374151; padding: 12px; border-radius: 8px; background-color: #1f2937; margin-bottom: 15px;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <span style="color: #9ca3af; font-size: 0.85rem; font-weight: 500;">Daemon Status:</span>
        <span style="background-color: {status_bg}; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;">
            {status_label}
        </span>
    </div>
""", unsafe_allow_html=True)

# Render Ingestion times
last_ingest_str = scheduler_state["last_ingestion"].strftime('%Y-%m-%d %H:%M:%S') if scheduler_state.get("last_ingestion") else "Never"
next_ingest_str = scheduler_state["next_ingestion"].strftime('%Y-%m-%d %H:%M:%S') if scheduler_state.get("next_ingestion") else "Pending"
# Render Scan times
last_scan_str = scheduler_state["last_scan"].strftime('%Y-%m-%d %H:%M:%S') if scheduler_state.get("last_scan") else "Never"
next_scan_str = scheduler_state["next_scan"].strftime('%Y-%m-%d %H:%M:%S') if scheduler_state.get("next_scan") else "Pending"

st.sidebar.markdown(f"""
<div style="font-size: 0.8rem; color: #9ca3af; line-height: 1.5;">
    <div style="margin-bottom: 5px; border-bottom: 1px solid #374151; padding-bottom: 5px;">
        <b style="color: #ffffff;">Ingestion Schedule</b>
        <div>Last Ingest: {last_ingest_str}</div>
        <div>Next Ingest: {next_ingest_str}</div>
    </div>
    <div>
        <b style="color: #ffffff;">Scanning Schedule</b>
        <div>Last Scan: {last_scan_str}</div>
        <div>Next Scan: {next_scan_str}</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("</div>", unsafe_allow_html=True)
st.sidebar.markdown("---")

# SCHEDULER CONTROLS
st.sidebar.markdown("### Scheduler Settings")
daemon_enabled = st.sidebar.checkbox("Enable Background Scanning", value=scheduler_state.get("enabled", True))
scheduler_state["enabled"] = daemon_enabled

ingest_interval = st.sidebar.slider(
    "Ingestion Interval (Minutes)",
    min_value=5,
    max_value=120,
    value=scheduler_state.get("ingestion_interval_minutes", 30),
    step=5
)
scheduler_state["ingestion_interval_minutes"] = ingest_interval

scan_interval = st.sidebar.slider(
    "Scan Interval (Minutes)",
    min_value=5,
    max_value=60,
    value=scheduler_state.get("scan_interval_minutes", 10),
    step=5
)
scheduler_state["scan_interval_minutes"] = scan_interval

max_post_age = st.sidebar.slider(
    "Max Post Age (Days)",
    min_value=1,
    max_value=30,
    value=scheduler_state.get("max_post_age_days", 3),
    step=1
)
scheduler_state["max_post_age_days"] = max_post_age

import re
from collections import Counter

def extract_hashtags_from_df(df_data):
    if df_data.empty or "text" not in df_data.columns:
        return Counter()
    all_hashtags = []
    for text in df_data["text"].dropna():
        tags = re.findall(r"#\w+", str(text))
        all_hashtags.extend([t.lower() for t in tags])
    return Counter(all_hashtags)

# Initialize session state for Custom Hashtag Mode
if "custom_mode_active" not in st.session_state:
    st.session_state["custom_mode_active"] = False
if "custom_mode_tags" not in st.session_state:
    st.session_state["custom_mode_tags"] = []

st.sidebar.markdown("---")

# SIDEBAR CONTROLS
st.sidebar.title("Controls & Filters")

# Trigger collection manually
if st.sidebar.button("Run Default Ingestion Now", use_container_width=True):
    run_ingestion()

if st.sidebar.button("Re-Scan Stored Records", use_container_width=True):
    try:
        updated_count = rescan_stored_data()
        st.success(f"Successfully re-scanned and updated {updated_count} stored posts!")
    except Exception as e:
        st.error(f"Re-scan failed: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("### 🏷️ Custom Hashtag Live Search")
custom_hashtag_input = st.sidebar.text_input(
    "Target Hashtag(s) / Keywords",
    placeholder="e.g. #corruption, #election2026",
    help="Enter individual or custom hashtags (comma-separated) to run an immediate live query across all platform collectors."
)

strict_mode_check = st.sidebar.checkbox(
    "🎯 Enable Custom Hashtag Mode",
    value=True,
    help="When enabled, only posts strictly containing your requested custom hashtag(s) will be ingested and displayed."
)

if st.sidebar.button("🔎 Search & Ingest Custom Hashtag", use_container_width=True):
    if custom_hashtag_input.strip():
        tags = [t.strip() for t in custom_hashtag_input.split(",") if t.strip()]
        st.session_state["custom_mode_active"] = strict_mode_check
        st.session_state["custom_mode_tags"] = tags
        run_ingestion(custom_keywords=tags, strict_hashtag_mode=strict_mode_check)
        st.rerun()
    else:
        st.sidebar.warning("Please enter at least one hashtag or term to search.")

if st.session_state.get("custom_mode_active") and st.session_state.get("custom_mode_tags"):
    tags_display = ", ".join(st.session_state["custom_mode_tags"])
    st.sidebar.markdown(f"""
    <div style="background-color: #1e3a8a; border: 1px solid #3b82f6; border-radius: 8px; padding: 10px; margin-top: 10px; margin-bottom: 10px;">
        <div style="color: #93c5fd; font-size: 0.75rem; font-weight: bold; text-transform: uppercase;">🎯 Custom Hashtag Mode Active</div>
        <div style="color: #ffffff; font-size: 0.85rem; margin-top: 4px;">Filtering strictly for: <b>{tags_display}</b></div>
    </div>
    """, unsafe_allow_html=True)
    
    if st.sidebar.button("❌ Exit Custom Hashtag Mode", use_container_width=True):
        st.session_state["custom_mode_active"] = False
        st.session_state["custom_mode_tags"] = []
        st.rerun()

st.sidebar.markdown("---")

df = load_data()

# Apply strict Custom Hashtag Mode filtering on full dataset if active
if st.session_state.get("custom_mode_active") and st.session_state.get("custom_mode_tags") and not df.empty and "text" in df.columns:
    cleaned_active_tags = [t.strip().lower().lstrip("#") for t in st.session_state["custom_mode_tags"] if t.strip()]
    if cleaned_active_tags:
        df = df[df["text"].apply(lambda txt: any(tag in str(txt).lower() for tag in cleaned_active_tags))]

hashtag_counts = extract_hashtags_from_df(df)
top_hashtags = [tag for tag, count in hashtag_counts.most_common(25)]

if df.empty:
    st.sidebar.warning("No records found matching criteria. Click 'Run Default Ingestion Now' or use Custom Hashtag Search.")
    platform_filter = []
    threat_filter = []
    selected_hashtags = []
    custom_text_filter = ""
    min_score = 0.0
else:
    platforms = df["platform"].unique()
    platform_filter = st.sidebar.multiselect("Select Platforms", options=platforms, default=platforms)
    
    labels = df["threat_label"].unique()
    threat_filter = st.sidebar.multiselect("Select Threat Categories", options=labels, default=labels)
    
    selected_hashtags = st.sidebar.multiselect(
        "Filter by Detected Hashtags",
        options=top_hashtags,
        default=[],
        help="Filter dashboard metrics and table by specific hashtags found in post content."
    )
    
    custom_text_filter = st.sidebar.text_input(
        "Search Post Text / Custom Tag",
        placeholder="Filter text e.g. #scam or keyword",
        help="Filter existing stored records by any text snippet or hashtag."
    )
    
    min_score = st.sidebar.slider("Min Threat Score", min_value=0.0, max_value=1.0, value=0.0, step=0.05)

# HEADER
st.title("NTK Party Social Media Threat Monitor")
st.markdown("Automated social listening, sentiment analysis, custom hashtag tracking, and threat monitoring for Naam Tamilar Katchi (NTK).")

if st.session_state.get("custom_mode_active") and st.session_state.get("custom_mode_tags"):
    st.info(f"🎯 **Custom Hashtag Mode Active:** Displaying only posts matching: `{', '.join(st.session_state['custom_mode_tags'])}`")

if not df.empty:
    # Filter DataFrame
    filtered_df = df[
        (df["platform"].isin(platform_filter)) &
        (df["threat_label"].isin(threat_filter)) &
        (df["threat_score"] >= min_score)
    ]
    
    if selected_hashtags:
        filtered_df = filtered_df[filtered_df['text'].apply(lambda x: any(tag.lower() in str(x).lower() for tag in selected_hashtags))]

    if custom_text_filter.strip():
        filter_term = custom_text_filter.strip().lower()
        filtered_df = filtered_df[filtered_df['text'].str.lower().str.contains(filter_term, regex=False, na=False)]

    # Display Top Detected Hashtags Bar
    if top_hashtags:
        st.markdown("##### 🏷️ Top Hashtags in Monitored Data:")
        badge_html = " ".join([
            f'<span style="background-color: #1f2937; border: 1px solid #374151; color: #3b82f6; padding: 4px 10px; border-radius: 12px; font-size: 0.82rem; margin-right: 6px; display: inline-block; margin-bottom: 6px;"><b>{tag}</b> ({cnt})</span>'
            for tag, cnt in hashtag_counts.most_common(12)
        ])
        st.markdown(f'<div style="margin-bottom: 15px;">{badge_html}</div>', unsafe_allow_html=True)
    
    # 1. METRICS CARDS ROW
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{len(filtered_df)}</div>
            <div class="metric-label">Total Posts Monitored</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        flagged_count = filtered_df["flagged"].sum()
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: #ef4444;">{flagged_count}</div>
            <div class="metric-label">High-Threat Alerts</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        avg_threat = filtered_df["threat_score"].mean() if len(filtered_df) > 0 else 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: #f59e0b;">{avg_threat:.2f}</div>
            <div class="metric-label">Average Threat Index</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        avg_sentiment = filtered_df["sentiment_score"].mean() if len(filtered_df) > 0 else 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: {'#10b981' if avg_sentiment >= 0 else '#ef4444'};">{avg_sentiment:.2f}</div>
            <div class="metric-label">Average Sentiment</div>
        </div>
        """, unsafe_allow_html=True)

    # Load target keywords for keyword heatmap/mentions matching
    target_keywords_str = os.getenv("TARGET_KEYWORDS", "")
    TARGET_KEYWORDS = [kw.strip() for kw in target_keywords_str.split(",") if kw.strip()]

    # Helper function to generate structured markdown reports
    def generate_summary_report(report_df, age_days):
        import io
        total_posts = len(report_df)
        critical_posts = report_df[report_df["threat_score"] >= 0.8]
        high_posts = report_df[(report_df["threat_score"] >= 0.5) & (report_df["threat_score"] < 0.8)]
        avg_threat = report_df["threat_score"].mean() if total_posts > 0 else 0.0
        avg_sentiment = report_df["sentiment_score"].mean() if total_posts > 0 else 0.0
        
        # Calculate active keywords mentions
        keyword_counts = {}
        for text in report_df["text"]:
            for kw in TARGET_KEYWORDS:
                if kw.lower() in text.lower():
                    keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        report = io.StringIO()
        report.write(f"# NAAM TAMILAR KATCHI (NTK) THREAT INTELLIGENCE ASSESSMENT REPORT\n")
        report.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Local Time)\n")
        report.write(f"Monitoring Timeframe: Last {age_days} Days\n\n")
        
        report.write(f"## 1. Executive Summary\n")
        report.write(f"This report assesses the current threat level, public sentiment, and hostile coordination trends targeting Naam Tamilar Katchi (NTK) on social media. The assessment covers the selected time window.\n\n")
        
        report.write(f"## 2. Key Metrics\n")
        report.write(f"- **Total Posts Monitored**: {total_posts}\n")
        report.write(f"- **Critical Severity Threats (Score >= 0.8)**: {len(critical_posts)}\n")
        report.write(f"- **High Severity Threats (Score 0.5 - 0.79)**: {len(high_posts)}\n")
        report.write(f"- **Average Threat Index**: {avg_threat:.2f}\n")
        report.write(f"- **Average Sentiment Score**: {avg_sentiment:.2f} (Scale: -1.0 to +1.0)\n\n")
        
        report.write(f"## 3. Top Active Keywords & Themes\n")
        if top_keywords:
            for kw, count in top_keywords:
                report.write(f"- **{kw}**: {count} mentions\n")
        else:
            report.write(f"No target monitoring keywords detected in active posts.\n")
        report.write(f"\n")
        
        report.write(f"## 4. Flagged High-Severity Incidents\n")
        flagged_df = report_df[report_df["threat_score"] >= 0.5].sort_values(by="threat_score", ascending=False)
        if not flagged_df.empty:
            for _, row in flagged_df.head(20).iterrows():
                severity = "CRITICAL" if row["threat_score"] >= 0.8 else "HIGH"
                report.write(f"### [{severity}] [{row['platform'].upper()}] {row['author_name']}\n")
                report.write(f"- **Published**: {row['published_at']}\n")
                report.write(f"- **Threat Score**: {row['threat_score']:.2f}\n")
                report.write(f"- **Threat Label**: {row['threat_label'].replace('_', ' ')}\n")
                report.write(f"- **Sentiment**: {row['sentiment_score']:.2f}\n")
                report.write(f"- **Source URL**: {row['url']}\n")
                report.write(f"- **Content Snippet**:\n  > {row['text']}\n\n")
        else:
            report.write(f"No high or critical severity alerts recorded in the current timeframe.\n")
            
        return report.getvalue()

    # Generate figures
    # 1. Threat distribution histogram
    fig_hist = px.histogram(
        filtered_df, 
        x="threat_score", 
        nbins=20, 
        title="Threat Score Distribution",
        color_discrete_sequence=['#3b82f6'],
        labels={"threat_score": "Threat Score"}
    )
    fig_hist.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    
    # 2. Platform breakdown pie chart
    fig_pie = px.pie(
        filtered_df, 
        names="platform", 
        title="Posts by Platform",
        color_discrete_sequence=px.colors.qualitative.Safe
    )
    fig_pie.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')

    # 3. Trend line chart
    filtered_df['published_hour'] = pd.to_datetime(filtered_df['published_at']).dt.strftime('%m-%d %H:00')
    trend_data = filtered_df.groupby(['published_hour', 'platform']).size().reset_index(name='count')
    fig_trend = px.line(
        trend_data, 
        x="published_hour", 
        y="count", 
        color="platform", 
        title="Post Volume Trends",
        markers=True
    )
    fig_trend.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')

    # 4. Sentiment Trend Line Chart
    sentiment_trend_data = filtered_df.groupby(['published_hour', 'platform'])['sentiment_score'].mean().reset_index()
    fig_sentiment_trend = px.line(
        sentiment_trend_data, 
        x="published_hour", 
        y="sentiment_score", 
        color="platform", 
        title="Average Sentiment Trends (Lower = More Hostile)",
        markers=True
    )
    fig_sentiment_trend.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')

    # 5. Platform Threat Box Plot
    fig_box = px.box(
        filtered_df, 
        x="platform", 
        y="threat_score", 
        color="platform",
        title="Threat Severity Range by Platform"
    )
    fig_box.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')

    # 6. Keyword Frequency bar chart
    keyword_counts = {}
    for text in filtered_df["text"]:
        for kw in TARGET_KEYWORDS:
            if kw.lower() in text.lower():
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
    if keyword_counts:
        kw_df = pd.DataFrame(list(keyword_counts.items()), columns=["Keyword", "Count"]).sort_values(by="Count", ascending=False).head(10)
        fig_keywords = px.bar(
            kw_df,
            x="Count",
            y="Keyword",
            orientation='h',
            title="Top 10 Active Keywords",
            color="Count",
            color_continuous_scale=px.colors.sequential.Viridis
        )
        fig_keywords.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', yaxis={'categoryorder':'total ascending'})
    else:
        fig_keywords = None

    # Declare Dashboard Tabs
    tab_feed, tab_analytics, tab_hostile, tab_exporter, tab_single_video = st.tabs([
        "Threat Intelligence Feed",
        "Advanced Analytics",
        "Hostile Channels Monitor",
        "Report Exporter",
        "Single Video Analyzer"
    ])

    with tab_feed:
        # Coordinated Behavior Network Graph
        st.markdown("### Coordinated Behavior Network Graph")
        st.markdown("Visualize connections between **Authors** (circles colored by platform), **Threat Categories** (purple stars), and **Target Keywords** (gold diamonds). Drag nodes to inspect links.")
        try:
            graph_html = render_network_graph(filtered_df)
            if graph_html:
                st.components.v1.html(graph_html, height=520)
            else:
                st.info("No active connections found to graph.")
        except Exception as e:
            st.error(f"Error rendering network graph: {e}")

        # Data Feed list
        st.markdown("### Threat Intelligence Feed")
        
        # Filtering & Sorting UI
        filter_col1, filter_col2, filter_col3 = st.columns([2, 1, 1])
        
        with filter_col1:
            search_query = st.text_input("Search posts by author, content, or platform", value="", placeholder="Type search term...")
            
        with filter_col2:
            sort_by = st.selectbox(
                "Sort Feed By",
                options=["Publish Date (Newest)", "Publish Date (Oldest)", "Threat Score (Highest)", "Threat Score (Lowest)", "Sentiment (Most Hostile)"]
            )
            
        with filter_col3:
            posts_per_page = st.selectbox(
                "Posts per page",
                options=[10, 25, 50, 100],
                index=0
            )
            
        # Apply search filter
        feed_df = filtered_df.copy()
        if search_query:
            search_query = search_query.lower()
            feed_df = feed_df[
                feed_df["author_name"].str.lower().str.contains(search_query) |
                feed_df["text"].str.lower().str.contains(search_query) |
                feed_df["platform"].str.lower().str.contains(search_query)
            ]
            
        # Apply sorting algorithm
        if sort_by == "Publish Date (Newest)":
            feed_df = feed_df.sort_values(by="published_at", ascending=False)
        elif sort_by == "Publish Date (Oldest)":
            feed_df = feed_df.sort_values(by="published_at", ascending=True)
        elif sort_by == "Threat Score (Highest)":
            feed_df = feed_df.sort_values(by="threat_score", ascending=False)
        elif sort_by == "Threat Score (Lowest)":
            feed_df = feed_df.sort_values(by="threat_score", ascending=True)
        elif sort_by == "Sentiment (Most Hostile)":
            feed_df = feed_df.sort_values(by="sentiment_score", ascending=True)
            
        # Display results count
        st.markdown(f"*Showing {len(feed_df)} matches*")
        
        # Stylized brand platform tag color map
        platform_pills = {
            "youtube": {"bg": "#ff0000", "label": "YouTube"},
            "twitter": {"bg": "#1da1f2", "label": "X/Twitter"},
            "facebook": {"bg": "#1877f2", "label": "Facebook"},
            "google_news": {"bg": "#4285f4", "label": "Google News"},
            "reddit": {"bg": "#ff4500", "label": "Reddit"},
            "mastodon": {"bg": "#563acc", "label": "Mastodon"},
            "telegram": {"bg": "#0088cc", "label": "Telegram"},
            "instagram": {"bg": "#e1306c", "label": "Instagram"},
            "main_media": {"bg": "#6b7280", "label": "Main Media"}
        }
        
        for idx, row in feed_df.head(posts_per_page).iterrows():
            # Dynamic threat severity badge color
            score = row['threat_score']
            if score >= 0.8:
                severity_color = "#ef4444"
                badge = "CRITICAL"
            elif score >= 0.5:
                severity_color = "#f59e0b"
                badge = "HIGH"
            else:
                severity_color = "#10b981"
                badge = "LOW"
                
            platform_info = platform_pills.get(row['platform'], {"bg": "#374151", "label": row['platform'].upper()})
            
            # Format dates nicely
            pub_date = row['published_at']
            if isinstance(pub_date, datetime.datetime):
                formatted_date = pub_date.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_date = str(pub_date)
                
            with st.container():
                st.markdown(f"""
                <div style="
                    border: 1px solid #374151; 
                    padding: 18px; 
                    border-radius: 12px; 
                    margin-bottom: 16px; 
                    background-color: #1f2937;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                ">
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; margin-bottom: 12px; gap: 8px;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="background-color: {platform_info['bg']}; color: white; padding: 4px 10px; border-radius: 9999px; font-weight: bold; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;">
                                {platform_info['label']}
                            </span>
                            <strong style="color: #f3f4f6; font-size: 1.15rem;">{row['author_name']}</strong> 
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <span style="background-color: {severity_color}; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 0.75rem; letter-spacing: 0.05em;">
                                {badge} ({score:.2f})
                            </span>
                            <span style="background-color: #4b5563; color: #e5e7eb; padding: 4px 10px; border-radius: 6px; font-weight: 500; font-size: 0.75rem; text-transform: capitalize;">
                                {row['threat_label'].replace('_', ' ')}
                            </span>
                        </div>
                    </div>
                    <div style="color: #e5e7eb; font-size: 1rem; line-height: 1.6; margin-bottom: 14px; background-color: rgba(255, 255, 255, 0.02); padding: 12px; border-radius: 8px; border-left: 3px solid #4b5563;">
                        {row['text']}
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; font-size: 0.8rem; color: #9ca3af; gap: 8px;">
                        <div>
                            <span>Published: {formatted_date}</span>
                            <span style="margin: 0 8px;">|</span>
                            <span>Sentiment: <span style="color: {'#ef4444' if row['sentiment_score'] < 0 else '#10b981'}; font-weight: bold;">{row['sentiment_score']:.2f}</span></span>
                        </div>
                        <div style="display: flex; gap: 10px;">
                            <a href="{row['url']}" target="_blank" style="color: #3b82f6; text-decoration: none; font-weight: bold; font-size: 0.85rem; border: 1px solid #3b82f6; padding: 4px 10px; border-radius: 6px; transition: background 0.2s;">
                                View Source Details
                            </a>
                            {f'<a href="?analyze={urllib.parse.quote(row["url"])}" target="_blank" style="color: #ffffff; background-color: #ef4444; text-decoration: none; font-weight: bold; font-size: 0.85rem; border: 1px solid #ef4444; padding: 4px 10px; border-radius: 6px; transition: background 0.2s;">Deep Dive: Analyze Comments</a>' if row['platform'] == 'youtube' else ''}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with tab_analytics:
        st.markdown("### Analytics & Distribution")
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.plotly_chart(fig_hist, use_container_width=True)
            st.plotly_chart(fig_trend, use_container_width=True)
        with chart_col2:
            st.plotly_chart(fig_pie, use_container_width=True)
            st.plotly_chart(fig_box, use_container_width=True)
            
        st.markdown("---")
        st.plotly_chart(fig_sentiment_trend, use_container_width=True)
        
        if fig_keywords is not None:
            st.markdown("---")
            st.plotly_chart(fig_keywords, use_container_width=True)
        else:
            st.info("No matching monitoring keywords detected in active feed dataset.")

    with tab_hostile:
        st.markdown("### Hostile Channels & Accounts Monitor")
        st.markdown("Automated detection of hostile accounts. Attacking profiles are added here automatically once flagged by the AI scanning pipeline, enabling dynamic auto-tracking of their new uploads.")
        
        from database.database import DBHostileChannel
        session = SessionLocal()
        try:
            hostile_query = session.query(DBHostileChannel).order_by(desc(DBHostileChannel.threat_count)).all()
            if not hostile_query:
                st.info("No hostile channels registered yet. Attacking accounts will appear here automatically as they are detected.")
            else:
                st.markdown("#### Monitored Accounts & Verification")
                
                # Header row
                h_col1, h_col2, h_col3, h_col4, h_col5 = st.columns([2, 1, 1, 1, 1])
                with h_col1:
                    st.markdown("**Channel Name (ID)**")
                with h_col2:
                    st.markdown("**Platform**")
                with h_col3:
                    st.markdown("**Flagged Attacks**")
                with h_col4:
                    st.markdown("**Avg Threat Index**")
                with h_col5:
                    st.markdown("**Tracking Action**")
                st.markdown("---")
                
                for chan in hostile_query:
                    col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns([2, 1, 1, 1, 1])
                    with col_c1:
                        st.write(f"**{chan.author_name}** ({chan.author_id})")
                    with col_c2:
                        st.write(f"`{chan.platform.upper()}`")
                    with col_c3:
                        st.write(f"{chan.threat_count} posts")
                    with col_c4:
                        st.write(f"{chan.avg_threat_score:.2f}")
                    with col_c5:
                        if chan.status == "active_monitoring":
                            if st.button("Ignore Source", key=f"ignore_{chan.id}", use_container_width=True):
                                db_chan = session.query(DBHostileChannel).filter(DBHostileChannel.id == chan.id).first()
                                db_chan.status = "ignored"
                                session.commit()
                                st.rerun()
                        else:
                            if st.button("Auto-Track", key=f"track_{chan.id}", use_container_width=True):
                                db_chan = session.query(DBHostileChannel).filter(DBHostileChannel.id == chan.id).first()
                                db_chan.status = "active_monitoring"
                                session.commit()
                                st.rerun()
        except Exception as e:
            st.error(f"Error loading hostile channels: {e}")
        finally:
            session.close()

    with tab_exporter:
        st.markdown("### Threat Intelligence Exporter")
        st.markdown("Generate and download summary reports based on active filtered threat records.")
        
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            st.markdown("#### Export Actions")
            # CSV Exporter
            csv_data = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Export Current Dataset (CSV)",
                data=csv_data,
                file_name=f"ntk_threats_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            # Markdown Exporter
            report_text = generate_summary_report(filtered_df, max_post_age)
            st.download_button(
                label="Export Summary Assessment Report (Markdown)",
                data=report_text,
                file_name=f"ntk_threat_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True
            )
            
        with col_exp2:
            st.markdown("#### Timeframe Summary Metrics")
            st.markdown(f"""
            - **Filter State**: Max Post Age ({max_post_age} days)
            - **Total Records In Scope**: {len(filtered_df)}
            - **Critical Alerts Flagged**: {len(filtered_df[filtered_df['threat_score'] >= 0.8])}
            - **High Alerts Flagged**: {len(filtered_df[(filtered_df['threat_score'] >= 0.5) & (filtered_df['threat_score'] < 0.8)])}
            - **Average Threat Index**: {filtered_df['threat_score'].mean() if len(filtered_df) > 0 else 0.0:.2f}
            - **Average Sentiment Score**: {filtered_df['sentiment_score'].mean() if len(filtered_df) > 0 else 0.0:.2f}
            """)
            
        st.markdown("---")
        st.markdown("#### Report Assessment Preview")
        st.text_area("Live Report Content Preview", value=report_text, height=400, disabled=True)

    with tab_single_video:
        st.markdown("### 🎯 Single Video Threat & Sentiment Analyzer")
        st.markdown("Analyze audience comments, viewer sentiment, threat levels, and engagement metrics for a specific YouTube video without relying on API quotas. Includes comprehensive Markdown report export, AI summary synthesis, and actionable steps.")
        
        sv_col_in, sv_col_slider = st.columns([3, 1])
        with sv_col_in:
            sv_url = st.text_input("YouTube Video URL", placeholder="e.g. https://www.youtube.com/watch?v=dQw4w9WgXcQ", key="tab_sv_url_input")
        with sv_col_slider:
            sv_sample_size = st.slider("Comments Sample Limit", min_value=10, max_value=100, value=30, step=10, key="tab_sv_sample_size")
            
        sv_btn_col1, sv_btn_col2 = st.columns([1, 1])
        with sv_btn_col1:
            run_in_page = st.button("🔍 Run Deep Dive Analysis (In-Page)", use_container_width=True, type="primary")
        with sv_btn_col2:
            if sv_url:
                st.markdown(f'<a href="?analyze={urllib.parse.quote(sv_url)}" target="_blank" style="display: block; text-align: center; color: #ffffff; background-color: #374151; text-decoration: none; font-weight: bold; font-size: 0.95rem; border: 1px solid #4b5563; padding: 8px 16px; border-radius: 6px; transition: background 0.2s;">Open in Standalone Tab ↗</a>', unsafe_allow_html=True)
            else:
                st.button("Open in Standalone Tab ↗", disabled=True, use_container_width=True)
                
        if run_in_page and sv_url:
            with st.spinner("Scraping video metadata and downloading real-time comments..."):
                try:
                    from collectors.youtube import fetch_single_video_data
                    from pipeline.classify import classify_and_score
                    
                    data = fetch_single_video_data(sv_url, max_comments=sv_sample_size)
                    video_post = data["video"]
                    raw_comments = data["comments"]
                    
                    processed_comments = []
                    for comment in raw_comments:
                        processed_comments.append(classify_and_score(comment))
                        
                    st.session_state["tab_single_video_data"] = {
                        "video_post": video_post,
                        "processed_comments": processed_comments
                    }
                except Exception as e:
                    st.error(f"Failed to analyze video: {str(e)}")
                    
        if "tab_single_video_data" in st.session_state and st.session_state["tab_single_video_data"]:
            sv_cached = st.session_state["tab_single_video_data"]
            render_single_video_analysis(sv_cached["video_post"], sv_cached["processed_comments"], is_standalone=False)
            
else:
    st.info("The database is currently empty. Please trigger 'Run Ingestion Now' in the sidebar to load simulated threat alerts and verify the dashboard visualizer.")

# RENDER FLOATING STATUS INDICATOR IN THE BOTTOM LEFT CORNER OF SCREEN
is_ingesting = ingestion_lock.locked()
is_scanning = scheduler_state.get("scan_active", False)

if is_ingesting:
    status_text = "Ingesting new posts..."
    dot_color = "#f59e0b"  # amber
elif is_scanning:
    status_text = "Scanning and classifying..."
    dot_color = "#8b5cf6"  # purple
else:
    status_text = "Background daemon active"
    dot_color = "#10b981"  # green
    
st.markdown(f"""
<div class="status-bubble">
    <div class="status-dot" style="background-color: {dot_color};"></div>
    <span>{status_text}</span>
</div>
<style>
    .status-bubble {{
        position: fixed;
        bottom: 20px;
        left: 20px;
        background-color: #1f2937;
        color: #e5e7eb;
        border: 1px solid #374151;
        padding: 8px 16px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 500;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.15), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
        z-index: 9999;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .status-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        animation: pulse-status 2s infinite;
    }}
    @keyframes pulse-status {{
        0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 {dot_color}88; }}
        70% {{ transform: scale(1); box-shadow: 0 0 0 5px {dot_color}00; }}
        100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 {dot_color}00; }}
    }}
</style>
""", unsafe_allow_html=True)
