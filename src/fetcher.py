"""
fetcher.py — pulls fresh "things people are building" from multiple sources.

Each source returns a list of DiscoveryItem. The main pipeline dedupes and
picks the best subset before passing to the summarizer.
"""

import logging
import re
import time
import requests
from typing import List

from .models import DiscoveryItem
from .config import Config

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Hacker News — recent Show HN via Algolia API
# ─────────────────────────────────────────────

def fetch_hackernews(max_items: int = 30, days: int = 7) -> List[DiscoveryItem]:
    """Fetch recent Show HN posts from the last `days` days, sorted by points."""
    cutoff = int(time.time()) - days * 86400
    url = "https://hn.algolia.com/api/v1/search"
    params = {
        "tags": "show_hn",
        "numericFilters": f"created_at_i>{cutoff}",
        "hitsPerPage": max_items,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
    except Exception as e:
        log.warning(f"HN fetch failed: {e}")
        return []

    items = []
    for hit in hits:
        hn_id = hit.get("objectID", "")
        title = hit.get("title", "").replace("Show HN: ", "").strip()
        story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hn_id}"
        items.append(
            DiscoveryItem(
                id=f"hn-{hn_id}",
                source="HackerNews",
                title=title,
                url=story_url,
                score=hit.get("points", 0),
                author=hit.get("author"),
                description=hit.get("story_text") or "",
            )
        )
    return items


# ─────────────────────────────────────────────
# Reddit — r/SideProject, r/InternetIsBeautiful via public JSON
# ─────────────────────────────────────────────

def fetch_reddit(subreddits: List[str], max_per_sub: int = 10) -> List[DiscoveryItem]:
    items: List[DiscoveryItem] = []
    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/top.json?t=week&limit={max_per_sub}"
        try:
            resp = requests.get(
                url, timeout=10, headers={"User-Agent": "discovery-bot/1.0"}
            )
            resp.raise_for_status()
            children = resp.json().get("data", {}).get("children", [])
        except Exception as e:
            log.warning(f"Reddit fetch failed for r/{sub}: {e}")
            continue

        for c in children:
            d = c.get("data", {})
            if d.get("stickied") or d.get("is_self") and not d.get("url_overridden_by_dest"):
                # Skip pinned & pure text posts without external link.
                if d.get("stickied"):
                    continue
            link = d.get("url_overridden_by_dest") or f"https://reddit.com{d.get('permalink', '')}"
            items.append(
                DiscoveryItem(
                    id=f"rd-{d.get('id')}",
                    source=f"Reddit/{sub}",
                    title=d.get("title", "").strip(),
                    url=link,
                    score=d.get("score", 0),
                    author=d.get("author"),
                    description=(d.get("selftext") or "")[:600],
                )
            )
    return items


# ─────────────────────────────────────────────
# Product Hunt — today's launches via GraphQL
# ─────────────────────────────────────────────

PRODUCTHUNT_GRAPHQL = "https://api.producthunt.com/v2/api/graphql"

PRODUCTHUNT_QUERY = """
query {
  posts(first: 20, order: VOTES) {
    edges {
      node {
        id
        name
        tagline
        url
        votesCount
        user { name }
        topics { edges { node { name } } }
      }
    }
  }
}
"""

def fetch_producthunt(api_key: str, max_items: int = 20) -> List[DiscoveryItem]:
    if not api_key:
        log.info("No Product Hunt API key configured, skipping.")
        return []
    try:
        resp = requests.post(
            PRODUCTHUNT_GRAPHQL,
            json={"query": PRODUCTHUNT_QUERY},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        edges = resp.json().get("data", {}).get("posts", {}).get("edges", [])
    except Exception as e:
        log.warning(f"ProductHunt fetch failed: {e}")
        return []

    items = []
    for edge in edges[:max_items]:
        node = edge["node"]
        topics = [t["node"]["name"] for t in node.get("topics", {}).get("edges", [])]
        items.append(
            DiscoveryItem(
                id=f"ph-{node['id']}",
                source="ProductHunt",
                title=node["name"],
                url=node["url"],
                score=node.get("votesCount", 0),
                author=node.get("user", {}).get("name"),
                description=node.get("tagline", ""),
                tags=topics,
            )
        )
    return items


# ─────────────────────────────────────────────
# GitHub Trending — scrape the trending page
# ─────────────────────────────────────────────

def fetch_github_trending(languages: list = None, max_items: int = 20) -> List[DiscoveryItem]:
    """
    GitHub has no official trending API, so we scrape the page.
    Optionally filter by language.
    """
    targets = languages or [""]  # empty string = all languages
    all_items = []

    # Real trending repo links live inside <h2 class="h3 lh-condensed"><a href="/owner/repo">.
    # Matching that wrapper avoids nav links like /sponsors/x or /trending/developers.
    repo_pattern = re.compile(
        r'<h2[^>]*class="h3 lh-condensed"[^>]*>\s*<a[^>]*href="/([^"/]+)/([^"]+)"',
        re.DOTALL,
    )
    star_pattern = re.compile(r'([\d,]+)\s*stars today')

    nav_prefixes = {"sponsors", "trending", "marketplace", "topics", "collections",
                    "explore", "settings", "notifications", "pulls", "issues"}

    for lang in targets:
        url = f"https://github.com/trending/{lang}?since=daily"
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "discovery-bot/1.0"})
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            log.warning(f"GitHub trending fetch failed for lang={lang!r}: {e}")
            continue

        matches = repo_pattern.findall(html)
        star_counts = star_pattern.findall(html)

        for i, (owner, name) in enumerate(matches[:max_items]):
            if owner in nav_prefixes:
                continue
            # name can contain extra path crumbs from sloppy HTML — keep first segment.
            name = name.split("/")[0]
            stars_today = int(star_counts[i].replace(",", "")) if i < len(star_counts) else 0
            slug = f"{owner}/{name}"
            all_items.append(
                DiscoveryItem(
                    id=f"gh-{owner}-{name}",
                    source="GitHubTrending",
                    title=slug,
                    url=f"https://github.com/{slug}",
                    score=stars_today,
                    author=owner,
                    description="",
                )
            )

    return all_items


# ─────────────────────────────────────────────
# Aggregate
# ─────────────────────────────────────────────

def fetch_all_sources(config: Config) -> List[DiscoveryItem]:
    items = []
    if config.enable_hackernews:
        items += fetch_hackernews()
    if config.enable_producthunt:
        items += fetch_producthunt(config.producthunt_api_key)
    if config.enable_github_trending:
        items += fetch_github_trending(config.github_languages)
    if config.enable_reddit:
        items += fetch_reddit(config.reddit_subs)
    return items
