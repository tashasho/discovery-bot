"""
models.py — shared data types used across fetcher, summarizer, and sender.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DiscoveryItem:
    """A single thing someone is building, before enrichment."""
    id: str                   # stable unique ID (e.g. "hn-12345678")
    source: str               # "HackerNews" | "ProductHunt" | "GitHubTrending"
    title: str
    url: str
    score: int                # raw popularity score from the source
    author: Optional[str] = None
    description: Optional[str] = None  # raw description from the source

    # Populated by summarizer
    summary: Optional[str] = None
    why_interesting: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    emoji: str = "🔧"         # summarizer picks a fitting emoji
