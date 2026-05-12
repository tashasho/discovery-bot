"""
slack_sender.py — formats and posts the digest to Slack using Block Kit.

Two delivery modes:
  1. Incoming Webhook (SLACK_WEBHOOK_URL) — easiest. No scopes, no install flow.
     Each webhook is bound to a single channel chosen at creation time.
  2. Bot Token (SLACK_BOT_TOKEN + SLACK_CHANNEL) — needed for slash commands,
     reactions listening, posting to arbitrary channels.
"""

import logging
from datetime import datetime
from typing import List

import requests

from .models import DiscoveryItem
from .config import Config

log = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"


SOURCE_ICONS = {
    "HackerNews": "🔶",
    "ProductHunt": "🐱",
    "GitHubTrending": "⭐",
}


def _icon_for(source: str) -> str:
    if source.startswith("Reddit/"):
        return "👽"
    return SOURCE_ICONS.get(source, "📡")


def _item_blocks(item: DiscoveryItem) -> list:
    source_icon = _icon_for(item.source)
    tags_str = " ".join(f"`{t}`" for t in item.tags) if item.tags else ""

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{item.emoji} *{item.title}*  {source_icon} _{item.source}_\n"
                    f"{item.summary}\n"
                    + (f"💡 _{item.why_interesting}_\n" if item.why_interesting else "")
                    + (f"{tags_str}" if tags_str else "")
                ),
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Open →", "emoji": True},
                "url": item.url,
                "action_id": f"open_{item.id}",
            },
        },
        {"type": "divider"},
    ]
    return blocks


def build_digest_blocks(items: List[DiscoveryItem], title: str = "🔭 Discovery Feed") -> list:
    today = datetime.now().strftime("%A, %B %-d")
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{title} — {today}",
                "emoji": True,
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Surfacing *{len(items)} interesting builds* from "
                        "Hacker News · Product Hunt · GitHub Trending  ·  "
                        "React with 👍 / 👎 to tune future picks."
                    ),
                }
            ],
        },
        {"type": "divider"},
    ]

    for item in items:
        blocks.extend(_item_blocks(item))

    blocks.append(
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "Summaries via OpenRouter · _discovery-bot_"}
            ],
        }
    )
    return blocks


def send_digest(items: List[DiscoveryItem], config: Config):
    config.require_slack()
    blocks = build_digest_blocks(items, title=config.digest_title)
    fallback = f"{config.digest_title} — {len(items)} interesting builds today"

    if config.slack_webhook_url:
        _send_via_webhook(config.slack_webhook_url, fallback, blocks)
    else:
        _send_via_bot(config.slack_bot_token, config.slack_channel, fallback, blocks)


def _send_via_webhook(webhook_url: str, fallback: str, blocks: list):
    resp = requests.post(
        webhook_url,
        json={"text": fallback, "blocks": blocks},
        timeout=15,
    )
    if resp.status_code != 200 or resp.text.strip() != "ok":
        log.error(f"Webhook post failed: {resp.status_code} {resp.text[:200]}")
        resp.raise_for_status()
        raise RuntimeError(f"Slack webhook returned non-ok: {resp.text!r}")
    log.info("Posted to Slack via webhook")


def _send_via_bot(token: str, channel: str, fallback: str, blocks: list):
    """Post via chat.postMessage using `requests` (bundles certifi, avoids macOS SSL issues)."""
    resp = requests.post(
        f"{SLACK_API}/chat.postMessage",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "channel": channel,
            "text": fallback,
            "blocks": blocks,
            "unfurl_links": False,
            "unfurl_media": False,
        },
        timeout=15,
    )
    data = resp.json()
    if not data.get("ok"):
        log.error(f"Slack post failed: {data.get('error')}")
        raise RuntimeError(f"Slack chat.postMessage failed: {data.get('error')}")
    log.info(f"Posted to #{channel} via bot token: ts={data['ts']}")
