"""seo-agent-team: six small agents that keep a WordPress site growing with researched, Rank Math 95+ articles.

  Strategist    picks the next article from real search data (Google suggestions, and Search Console queries the
                site nearly ranks for), never repeating a keyword.
  Writer        researches sourced facts and writes the article.
  Editor        checks it against Rank Math's tests and fixes it until it scores 95+. Publishes only if it passes;
                anything that falls short goes to a human (the approve() hook) instead of going live.
  Indexer       tells Bing about every new or updated page straight away and resubmits the sitemap to Google.
  Rank Tracker  impressions, clicks, average position and top searches for every article, plus index status.
  Refresher     rewrites an article that Google shows on page 2 or 3 around the searches people really use.
"""
from pathlib import Path

from . import settings

__version__ = "1.0.0"


def home() -> Path:
    d = settings.DATA_DIR
    for sub in ("", "drafts", "images"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d
