"""
config.py — all settings loaded from environment variables.
Copy .env.example to .env and fill in your values.

The only hard requirement is OPENROUTER_API_KEY. SLACK_BOT_TOKEN /
SLACK_WEBHOOK_URL are checked at send time, so --dry-run works without them.
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # ── LLM (OpenRouter; OpenAI-compatible) ──
    openrouter_api_key: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "")
    )
    # OpenRouter model slugs: https://openrouter.ai/models
    # Cheap/fast defaults that handle JSON well:
    #   "openai/gpt-4o-mini"             — fast, cheap, reliable JSON
    #   "anthropic/claude-3.5-haiku"     — Claude-flavored, cheap
    #   "google/gemini-2.0-flash-001"    — very cheap
    #   "meta-llama/llama-3.3-70b-instruct"
    model: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    )

    # ── Slack delivery ──
    # Either set SLACK_BOT_TOKEN + SLACK_CHANNEL (full bot),
    # OR set SLACK_WEBHOOK_URL (incoming webhook — much simpler, no scopes/install).
    slack_bot_token: str = field(default_factory=lambda: os.getenv("SLACK_BOT_TOKEN", ""))
    slack_channel: str = field(default_factory=lambda: os.getenv("SLACK_CHANNEL", "discovery-feed"))
    slack_webhook_url: str = field(default_factory=lambda: os.getenv("SLACK_WEBHOOK_URL", ""))

    # ── Bot behaviour ──
    picks_per_digest: int = field(default_factory=lambda: int(os.getenv("PICKS_PER_DIGEST", "5")))
    daily_post_time: str = field(default_factory=lambda: os.getenv("DAILY_POST_TIME", "09:00"))
    digest_title: str = field(default_factory=lambda: os.getenv("DIGEST_TITLE", "🔭 Discovery Feed"))

    # ── Source toggles ──
    enable_hackernews: bool = field(default_factory=lambda: _bool("ENABLE_HN"))
    enable_producthunt: bool = field(default_factory=lambda: _bool("ENABLE_PH"))
    enable_github_trending: bool = field(default_factory=lambda: _bool("ENABLE_GITHUB"))
    enable_reddit: bool = field(default_factory=lambda: _bool("ENABLE_REDDIT", default="false"))

    # GitHub Trending — filter by language (empty = all)
    github_languages: List[str] = field(
        default_factory=lambda: [
            l.strip() for l in os.getenv("GITHUB_LANGUAGES", "").split(",") if l.strip()
        ]
    )

    # Reddit — comma-separated subreddit names (no r/ prefix)
    reddit_subs: List[str] = field(
        default_factory=lambda: [
            s.strip() for s in os.getenv("REDDIT_SUBS", "SideProject,InternetIsBeautiful").split(",") if s.strip()
        ]
    )

    # Product Hunt API (optional — skipped if blank)
    producthunt_api_key: str = field(default_factory=lambda: os.getenv("PRODUCTHUNT_API_KEY", ""))

    # State persistence
    state_file: str = field(default_factory=lambda: os.getenv("STATE_FILE", "data/seen.json"))

    def require_llm(self):
        if not self.openrouter_api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Add it to .env. "
                "Get a key at https://openrouter.ai/keys"
            )

    def require_slack(self):
        if not self.slack_bot_token and not self.slack_webhook_url:
            raise RuntimeError(
                "No Slack destination configured. Set SLACK_WEBHOOK_URL (easy) "
                "or SLACK_BOT_TOKEN + SLACK_CHANNEL (full bot). "
                "Run with --dry-run to test without Slack."
            )
