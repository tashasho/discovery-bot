"""
Discovery Bot — main entry point.

Usage:
    python main.py                  # fetch, summarize, post to Slack once
    python main.py --dry-run        # print to terminal (no Slack required)
    python main.py --html out.html  # write a styled HTML preview file
    python main.py --loop           # run on a daily schedule
    python main.py --setup          # interactive .env wizard
"""

import argparse
import logging
import sys
import time

import schedule

from src.fetcher import fetch_all_sources
from src.summarizer import summarize_items
from src.slack_sender import send_digest
from src.state import SeenState
from src.config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def run_digest(dry_run: bool = False, html_path: str | None = None):
    log.info("Starting discovery run...")
    config = Config()
    config.require_llm()
    if not dry_run and not html_path:
        config.require_slack()

    state = SeenState(config.state_file)

    raw_items = fetch_all_sources(config)
    log.info(f"Fetched {len(raw_items)} raw items")

    fresh_items = [item for item in raw_items if not state.has_seen(item.id)]
    log.info(f"{len(fresh_items)} new items after dedup")

    if not fresh_items:
        log.info("Nothing new to share. Skipping.")
        return

    top_items = sorted(fresh_items, key=lambda x: x.score, reverse=True)[: config.picks_per_digest]
    log.info(f"Top {len(top_items)} picks selected; summarizing with {config.model}...")

    enriched = summarize_items(top_items, config)

    if dry_run:
        _print_terminal(enriched)
    if html_path:
        _write_html(enriched, html_path, config)
        log.info(f"HTML preview written to {html_path}")
    if not dry_run and not html_path:
        send_digest(enriched, config)

    for item in enriched:
        state.mark_seen(item.id)
    state.save()
    log.info("Done.")


def _print_terminal(items):
    for item in items:
        print("\n" + "─" * 70)
        print(f"{item.emoji} {item.title}  [{item.source}]  ⭐ {item.score}")
        print(f"  {item.url}")
        if item.summary:
            print(f"  📝 {item.summary}")
        if item.why_interesting:
            print(f"  💡 {item.why_interesting}")
        if item.tags:
            print(f"  🏷️  {', '.join(item.tags)}")
    print()


def _write_html(items, path: str, config: Config):
    from datetime import datetime

    rows = []
    for it in items:
        tags = " ".join(f'<code>{t}</code>' for t in (it.tags or []))
        why = f'<p class="why">💡 {it.why_interesting}</p>' if it.why_interesting else ""
        rows.append(
            f"""
            <article>
              <h2>{it.emoji} <a href="{it.url}" target="_blank">{it.title}</a>
                  <span class="src">{it.source} · ⭐ {it.score}</span></h2>
              <p class="sum">{it.summary or ""}</p>
              {why}
              <p class="tags">{tags}</p>
            </article>
            """
        )
    today = datetime.now().strftime("%A, %B %d, %Y")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{config.digest_title} — {today}</title>
  <style>
    body {{ font: 16px/1.55 -apple-system, system-ui, sans-serif; max-width: 720px;
           margin: 40px auto; padding: 0 20px; color: #1f2328; background: #fafafa; }}
    h1 {{ font-size: 28px; margin-bottom: 4px; }}
    .meta {{ color: #6e7781; margin-bottom: 32px; }}
    article {{ background: #fff; border: 1px solid #d0d7de; border-radius: 12px;
               padding: 20px 24px; margin-bottom: 18px; }}
    article h2 {{ font-size: 18px; margin: 0 0 6px; }}
    article h2 a {{ color: #0969da; text-decoration: none; }}
    .src {{ font-size: 13px; font-weight: normal; color: #6e7781; margin-left: 8px; }}
    .sum {{ margin: 6px 0; }}
    .why {{ color: #4b5563; font-style: italic; margin: 4px 0; }}
    .tags code {{ background: #eef0f4; padding: 2px 6px; border-radius: 4px;
                  margin-right: 4px; font-size: 13px; }}
    footer {{ color: #6e7781; font-size: 13px; margin-top: 24px; text-align: center; }}
  </style>
</head>
<body>
  <h1>{config.digest_title}</h1>
  <p class="meta">{today} · {len(items)} picks</p>
  {''.join(rows)}
  <footer>Summaries via OpenRouter · discovery-bot</footer>
</body>
</html>
"""
    with open(path, "w") as f:
        f.write(html)


def setup_wizard():
    """Interactive .env creator."""
    import os
    from pathlib import Path

    env_path = Path(".env")
    if env_path.exists():
        ans = input(".env already exists. Overwrite? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            return

    print("\n── discovery-bot setup ──\n")
    openrouter = input("OpenRouter API key (https://openrouter.ai/keys): ").strip()
    model = input("Model slug [openai/gpt-4o-mini]: ").strip() or "openai/gpt-4o-mini"

    print("\nSlack delivery: pick one")
    print("  1) Incoming Webhook  (easiest — no app install)")
    print("  2) Bot token + channel")
    print("  3) Skip (run with --dry-run only)")
    choice = input("Choose [1/2/3]: ").strip()

    slack_lines = []
    if choice == "1":
        url = input("Slack incoming webhook URL: ").strip()
        slack_lines.append(f"SLACK_WEBHOOK_URL={url}")
    elif choice == "2":
        token = input("Bot token (xoxb-...): ").strip()
        ch = input("Channel name (no #) [discovery-feed]: ").strip() or "discovery-feed"
        slack_lines.append(f"SLACK_BOT_TOKEN={token}")
        slack_lines.append(f"SLACK_CHANNEL={ch}")

    picks = input("Picks per digest [5]: ").strip() or "5"

    lines = [
        "# discovery-bot — generated by --setup",
        f"OPENROUTER_API_KEY={openrouter}",
        f"OPENROUTER_MODEL={model}",
        *slack_lines,
        f"PICKS_PER_DIGEST={picks}",
        "DAILY_POST_TIME=09:00",
        "ENABLE_HN=true",
        "ENABLE_PH=true",
        "ENABLE_GITHUB=true",
        "GITHUB_LANGUAGES=",
        "STATE_FILE=data/seen.json",
        "DIGEST_TITLE=🔭 Discovery Feed",
    ]
    env_path.write_text("\n".join(lines) + "\n")
    print(f"\n✅ Wrote {env_path.absolute()}")
    print("Try: python main.py --dry-run")


def main():
    parser = argparse.ArgumentParser(description="Discovery Bot")
    parser.add_argument("--loop", action="store_true", help="Run on a daily schedule")
    parser.add_argument("--dry-run", action="store_true", help="Print to terminal, don't post")
    parser.add_argument("--html", metavar="PATH", help="Write HTML preview to PATH instead of posting")
    parser.add_argument("--setup", action="store_true", help="Interactive .env wizard")
    args = parser.parse_args()

    if args.setup:
        setup_wizard()
        return

    if args.loop:
        config = Config()
        log.info(f"Scheduling daily digest at {config.daily_post_time}")
        schedule.every().day.at(config.daily_post_time).do(
            run_digest, dry_run=args.dry_run, html_path=args.html
        )
        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        try:
            run_digest(dry_run=args.dry_run, html_path=args.html)
        except RuntimeError as e:
            log.error(str(e))
            sys.exit(1)


if __name__ == "__main__":
    main()
