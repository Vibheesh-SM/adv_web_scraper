import os
import requests
from dotenv import load_dotenv
from pipeline.schema import Post

load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def dispatch_alert(post: Post):
    """
    Sends alerts to Slack and Discord webhooks if they are configured.
    This uses free incoming webhooks and avoids any subscription costs.
    """
    if not post.flagged:
        return
        
    message_text = (
        f"**High Threat Detected!**\n"
        f"**Platform:** {post.platform.upper()}\n"
        f"**Author:** {post.author_name}\n"
        f"**Threat Label:** {post.threat_label}\n"
        f"**Threat Score:** {post.threat_score:.2f}\n"
        f"**Sentiment Score:** {post.sentiment_score:.2f}\n"
        f"**Link:** {post.url}\n"
        f"**Post Content:**\n> {post.text}"
    )

    # 1. Dispatch to Slack if webhook configured
    if SLACK_WEBHOOK_URL and "hooks.slack.com" in SLACK_WEBHOOK_URL:
        try:
            payload = {
                "text": f"*High Threat Detected on {post.platform.upper()}!*",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"*High Threat Detected!*\n"
                                f"*Platform:* {post.platform.upper()}\n"
                                f"*Author:* {post.author_name}\n"
                                f"*Threat Classification:* `{post.threat_label}`\n"
                                f"*Score:* `{post.threat_score:.2f}`\n"
                                f"*Link:* <{post.url}|View Original Post>\n\n"
                                f"*Content:*\n> {post.text}"
                            )
                        }
                    }
                ]
            }
            res = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
            if res.status_code == 200:
                print(f"[Alerts] Successfully sent Slack alert for post {post.post_id}")
            else:
                print(f"[Alerts] Slack hook returned error code {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[Alerts] Failed to send Slack alert: {e}")

    # 2. Dispatch to Discord if webhook configured
    if DISCORD_WEBHOOK_URL and "discord.com" in DISCORD_WEBHOOK_URL:
        try:
            payload = {
                "content": message_text
            }
            res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
            if res.status_code in (200, 204):
                print(f"[Alerts] Successfully sent Discord alert for post {post.post_id}")
            else:
                print(f"[Alerts] Discord hook returned error code {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[Alerts] Failed to send Discord alert: {e}")

if __name__ == "__main__":
    # Test alert payload
    test_flagged_post = Post(
        post_id="test_alert_1",
        platform="youtube",
        text="This company is running a massive scam! Stay away at all costs!",
        author_id="user_scam_hunter",
        author_name="ScamHunter",
        published_at=None,
        url="https://youtube.com/watch?v=123",
        threat_score=0.89,
        threat_label="smear_campaign",
        sentiment_score=-0.75,
        flagged=True
    )
    dispatch_alert(test_flagged_post)
