"""
summarizer.py — calls an LLM via OpenRouter to enrich each DiscoveryItem.

OpenRouter is an OpenAI-compatible router that lets you use Claude, GPT, Gemini,
Llama, etc. with one key. We use the OpenAI SDK pointed at OpenRouter's base URL.

Each item gets:
  - A 2-sentence plain-English summary
  - A "why this is interesting" hook
  - 2–3 category tags
  - A fitting emoji

Processes items in parallel for speed.
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

from openai import OpenAI

from .models import DiscoveryItem
from .config import Config

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a sharp, curious technologist who spots interesting projects early.
Your job is to read raw information about something someone is building and produce a concise,
insightful summary for a tech-savvy audience.

Respond ONLY with a valid JSON object — no markdown, no commentary, no wrapping backticks.
The JSON must have these exact keys:
  - "summary":          string, 2 sentences max, plain English, what it is and what it does
  - "why_interesting":  string, 1 sentence, what makes this notable or timely RIGHT NOW
  - "tags":             array of 2–3 lowercase strings (e.g. ["ai", "dev-tools", "open-source"])
  - "emoji":            string, single emoji that best represents the project

Be direct. Avoid hype words like "revolutionary", "game-changing", "innovative".
If you have no information, say what you can infer from the title alone."""


def _build_prompt(item: DiscoveryItem) -> str:
    parts = [
        f"Source: {item.source}",
        f"Title: {item.title}",
    ]
    if item.author:
        parts.append(f"Author: {item.author}")
    if item.description:
        parts.append(f"Description: {item.description[:600]}")
    if item.tags:
        parts.append(f"Tags from source: {', '.join(item.tags)}")
    parts.append(f"URL: {item.url}")
    return "\n".join(parts)


def _extract_json(raw: str) -> dict:
    """Models sometimes wrap JSON in ```json ... ``` despite instructions. Strip it."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def _enrich_item(item: DiscoveryItem, client: OpenAI, model: str) -> DiscoveryItem:
    raw = ""
    try:
        completion = client.chat.completions.create(
            model=model,
            max_tokens=400,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(item)},
            ],
        )
        raw = completion.choices[0].message.content or ""
        data = _extract_json(raw)

        item.summary = data.get("summary", item.description or item.title)
        item.why_interesting = data.get("why_interesting", "")
        item.tags = data.get("tags", item.tags) or item.tags
        item.emoji = data.get("emoji", "🔧")
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse failed for {item.id}: {e} | raw: {raw[:200]}")
        item.summary = item.description or item.title
    except Exception as e:
        log.warning(f"Summarization failed for {item.id}: {e}")
        item.summary = item.description or item.title

    return item


def _make_client(config: Config) -> OpenAI:
    return OpenAI(
        api_key=config.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://github.com/local/discovery-bot",
            "X-Title": "discovery-bot",
        },
    )


def summarize_items(items: List[DiscoveryItem], config: Config) -> List[DiscoveryItem]:
    """Enrich all items concurrently. Returns enriched list in original order."""
    client = _make_client(config)

    enriched: List[DiscoveryItem] = [None] * len(items)  # type: ignore
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_idx = {
            executor.submit(_enrich_item, item, client, config.model): i
            for i, item in enumerate(items)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            enriched[idx] = future.result()

    return enriched
