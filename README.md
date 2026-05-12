# 🔭 discovery-bot

A Slackbot (or HTML newsletter, or terminal feed) that surfaces interesting things people are
building — Show HN, Product Hunt, GitHub Trending, Reddit r/SideProject — summarized by an LLM
of your choice via [OpenRouter](https://openrouter.ai) and delivered however you like.

## ⚡️ Fastest path to running (≈3 minutes)

```bash
cd slackbot-tashasho
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Interactive: walks you through .env (OpenRouter key, Slack choice, etc.)
python main.py --setup

# Just preview in your terminal — no Slack required
python main.py --dry-run

# Generate an HTML preview file
python main.py --html preview.html && open preview.html
```

You only **need** an OpenRouter key to see any output. Slack is layered on top.

## Three ways to deliver the digest

| Mode | What you need | Best for |
|---|---|---|
| `--dry-run` | nothing | testing, iterating on the prompt |
| `--html FILE` | nothing | newsletter, email, RSS, archive |
| Slack **webhook** | `SLACK_WEBHOOK_URL` only | one-channel posting, **easiest** |
| Slack **bot token** | `SLACK_BOT_TOKEN` + `SLACK_CHANNEL` | multiple channels, slash commands, reactions |

### Easiest Slack setup — Incoming Webhook (5 minutes)

1. Workspace → **Apps** → search **"Incoming Webhooks"** → Add to Slack
2. Pick the channel you want posts to go to
3. Copy the webhook URL → paste into `.env` as `SLACK_WEBHOOK_URL=...`
4. Sanity check: `python verify_slack.py`
5. Post: `python main.py`

That's the entire setup. No OAuth flow, no scopes to configure, no bot install.

### Full bot setup (slash commands, reactions, multi-channel)

1. [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch
2. **OAuth & Permissions** → add Bot Token Scope `chat:write`
3. Install to workspace → copy **Bot User OAuth Token** (`xoxb-...`)
4. In Slack: `/invite @your-bot-name` in the target channel
5. Put `SLACK_BOT_TOKEN` and `SLACK_CHANNEL` in `.env`, run `python verify_slack.py`

---

## Configuration

Everything lives in `.env` — copy `.env.example` to start, or run `python main.py --setup`.

| Variable | Default | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | — | **Required.** Get one at [openrouter.ai/keys](https://openrouter.ai/keys) |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Any slug from [openrouter.ai/models](https://openrouter.ai/models) |
| `SLACK_WEBHOOK_URL` | — | Webhook delivery path |
| `SLACK_BOT_TOKEN` | — | Bot token delivery path |
| `SLACK_CHANNEL` | `discovery-feed` | Channel name (no `#`) or ID |
| `PICKS_PER_DIGEST` | `5` | Items per digest |
| `DAILY_POST_TIME` | `09:00` | 24h, server local time, used by `--loop` |
| `DIGEST_TITLE` | `🔭 Discovery Feed` | Customize the header |
| `ENABLE_HN` / `ENABLE_PH` / `ENABLE_GITHUB` / `ENABLE_REDDIT` | first three on, Reddit off | Source toggles |
| `GITHUB_LANGUAGES` | empty (all) | Comma-separated, e.g. `python,rust,typescript` |
| `REDDIT_SUBS` | `SideProject,InternetIsBeautiful` | Comma-separated subreddit names |
| `PRODUCTHUNT_API_KEY` | — | Optional. Without it, PH is skipped silently. |

### Picking a model

For summarization, you want fast + cheap + reliable-JSON. All work well:

- `openai/gpt-4o-mini` — default, very cheap, ~$0.001/digest
- `anthropic/claude-3.5-haiku` — Claude-flavored summaries
- `google/gemini-2.0-flash-001` — cheapest
- `meta-llama/llama-3.3-70b-instruct` — open-weights

Switch models any time by editing `OPENROUTER_MODEL` — no code changes.

---

## Deploy (keep it running)

### GitHub Actions cron — free, zero infrastructure

```yaml
# .github/workflows/digest.yml
on:
  schedule:
    - cron: '0 14 * * *'   # 14:00 UTC = 9am ET, etc.
  workflow_dispatch:        # manual trigger
jobs:
  digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
      - uses: actions/upload-artifact@v4   # so dedup state survives runs
        with: { name: state, path: data/seen.json }
```

Add your secrets in **Settings → Secrets and variables → Actions**.

> Note: the artifact pattern above is a quick hack. For real persistence, commit `data/seen.json`
> back, or swap the JSON state file for a tiny SQLite hosted on Turso/Neon.

### Always-on host (Railway / Render / Fly.io / a VPS)

```
python main.py --loop
```

`--loop` runs forever, posting once per day at `DAILY_POST_TIME`.

---

## Extending

| What | Where |
|---|---|
| Add a new source | `src/fetcher.py` — add a `fetch_*` function, call it in `fetch_all_sources` |
| Change summary style | Edit `SYSTEM_PROMPT` in `src/summarizer.py` |
| Change Slack layout | Edit `_item_blocks` / `build_digest_blocks` in `src/slack_sender.py` |
| Slash commands | Add a Slack Bolt app in `app.py` with Socket Mode + your bot token |
| Reactions personalization | Listen to `reaction_added` events, weight future picks per tag |
| Different output format | Add a function in `main.py` alongside `_write_html` (Markdown, RSS, …) |

---

## Project structure

```
slackbot-tashasho/
├── main.py              # CLI entry: --dry-run / --html / --loop / --setup
├── verify_slack.py      # one-shot Slack credentials check
├── src/
│   ├── config.py        # all env-var driven settings
│   ├── models.py        # DiscoveryItem dataclass
│   ├── fetcher.py       # HN / PH / GitHub / Reddit sources
│   ├── summarizer.py    # OpenRouter (OpenAI-compatible) enrichment, parallel
│   ├── slack_sender.py  # Webhook + bot-token Slack delivery
│   └── state.py         # seen-items dedup, capped at 2000
├── data/
│   └── seen.json        # auto-created; tracks sent items
├── requirements.txt
├── .env.example
└── .env                 # you create this (gitignored)
```
