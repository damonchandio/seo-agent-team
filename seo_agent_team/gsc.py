"""Google Search Console (free): search queries you nearly rank for, rankings per page, and index status.

Uses a service account, so there's no sign-in that expires: create one in Google Cloud, download its JSON key, point
SEO_GSC_KEY_FILE at it, and add the service account's email as a user on your Search Console property.
"""
import datetime as dt
import logging
import re
import threading
from pathlib import Path

import requests

from . import settings

log = logging.getLogger("seo_agent_team")
SCOPES = ["https://www.googleapis.com/auth/webmasters"]  # read rankings and index status, resubmit the sitemap
_svc = None
lock = threading.Lock()  # the Google client isn't thread-safe


def ready() -> bool:
    return bool(settings.GSC_SITE and settings.GSC_KEY_FILE and Path(settings.GSC_KEY_FILE).exists())


def service():
    global _svc
    if _svc is None:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(settings.GSC_KEY_FILE, scopes=SCOPES)
        _svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    return _svc


def rows(dims: list[str], days: int, limit: int = 1000) -> list[dict]:
    end = dt.date.today() - dt.timedelta(days=2)       # Search Console data lags about two days
    body = {"startDate": str(end - dt.timedelta(days=days)), "endDate": str(end), "dimensions": dims,
            "rowLimit": limit}
    with lock:
        return service().searchanalytics().query(siteUrl=settings.GSC_SITE, body=body).execute().get("rows", [])


def opportunities(days: int = 28, limit: int = 25) -> list[dict]:
    """Queries with impressions where you sit around page 1-3: the easiest wins for a new article."""
    out = [{"query": r["keys"][0], "impressions": r["impressions"], "clicks": r["clicks"],
            "position": round(r["position"], 1)} for r in rows(["query"], days, 250) if 4 <= r["position"] <= 35]
    return sorted(out, key=lambda r: -r["impressions"])[:limit]


def submit_sitemap() -> None:
    with lock:
        service().sitemaps().submit(siteUrl=settings.GSC_SITE,
                                    feedpath=settings.SITE_URL.rstrip("/") + "/sitemap_index.xml").execute()


def sitemap_urls(limit: int = 150) -> list[str]:
    base = settings.SITE_URL.rstrip("/")
    try:
        idx = requests.get(base + "/sitemap_index.xml", timeout=30).text
    except requests.RequestException:
        return []
    maps = [u for u in re.findall(r"<loc>([^<]+)</loc>", idx) if re.search(r"(post|page)-sitemap", u)]
    urls = []
    for m in maps:
        try:
            urls += re.findall(r"<loc>([^<]+)</loc>", requests.get(m, timeout=30).text)
        except requests.RequestException:
            continue
    return [u for u in dict.fromkeys(urls) if not re.search(r"\.(png|jpe?g|webp|gif)$", u)][:limit]


def inspect(url: str) -> dict:
    with lock:
        r = service().urlInspection().index().inspect(body={"inspectionUrl": url, "siteUrl": settings.GSC_SITE}).execute()
    res = (r.get("inspectionResult") or {}).get("indexStatusResult") or {}
    return {"url": url, "verdict": res.get("verdict"), "state": res.get("coverageState"),
            "last_crawl": res.get("lastCrawlTime")}


def index_report() -> str:
    urls = sitemap_urls()
    if not urls:
        return "I couldn't read the sitemap at /sitemap_index.xml."
    missing = []
    for u in urls:
        try:
            r = inspect(u)
        except Exception as e:  # noqa: BLE001
            return f"Search Console refused the check ({str(e)[:150]}). Is the service account added as a user?"
        if r["verdict"] != "PASS":
            missing.append(r)
    if not missing:
        return f"Index check: all {len(urls)} pages are on Google."
    lines = "\n".join(f"- {m['url']} ({m['state'] or 'unknown'})" for m in missing[:15])
    return (f"Index check: {len(urls) - len(missing)} of {len(urls)} pages are on Google. Not indexed yet:\n{lines}\n\n"
            "For each, open Search Console > URL inspection, paste the link, and choose Request indexing.")
