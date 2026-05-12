"""
verify_slack.py — sanity-check your Slack setup BEFORE running the full digest.

Uses `requests` (which bundles certifi) so it works on macOS Python.org installs
that otherwise fail SSL verification.
"""

import sys

import requests

from src.config import Config

SLACK_API = "https://slack.com/api"


def main():
    config = Config()
    try:
        config.require_slack()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if config.slack_webhook_url:
        print("Testing webhook delivery...")
        resp = requests.post(
            config.slack_webhook_url,
            json={"text": "✅ discovery-bot webhook test — you're good to go."},
            timeout=10,
        )
        if resp.status_code == 200 and resp.text.strip() == "ok":
            print("✅ Webhook works. Check the channel — you should see the test message.")
        else:
            print(f"❌ Webhook failed: {resp.status_code} {resp.text!r}")
            sys.exit(1)
        return

    token = config.slack_bot_token
    print(f"Testing bot token against #{config.slack_channel}...")

    auth = requests.post(
        f"{SLACK_API}/auth.test",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    ).json()
    if not auth.get("ok"):
        print(f"❌ auth.test failed: {auth.get('error')}")
        sys.exit(1)
    print(f"  Bot: {auth.get('user')} in workspace {auth.get('team')}")

    resp = requests.post(
        f"{SLACK_API}/chat.postMessage",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json={
            "channel": config.slack_channel,
            "text": "✅ discovery-bot bot-token test — you're good to go.",
        },
        timeout=15,
    ).json()
    if resp.get("ok"):
        print(f"✅ Posted to #{config.slack_channel} (ts={resp['ts']})")
        return

    err = resp.get("error", "unknown")
    hints = {
        "not_in_channel": (
            "Bot isn't in the channel. In Slack, run /invite @your-bot-name in "
            f"#{config.slack_channel}."
        ),
        "channel_not_found": (
            f"Channel '{config.slack_channel}' doesn't exist or the bot can't see it. "
            "Try a public channel name, or a channel ID (Cxxxxxx)."
        ),
        "invalid_auth": "SLACK_BOT_TOKEN is wrong or revoked.",
        "missing_scope": "Bot is missing the 'chat:write' scope. Reinstall with that scope.",
    }
    print(f"❌ chat.postMessage failed: {err}")
    if err in hints:
        print(f"   Hint: {hints[err]}")
    sys.exit(1)


if __name__ == "__main__":
    main()
