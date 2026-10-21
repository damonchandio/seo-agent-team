"""The team's jobs: Strategist, Writer + Editor, Indexer, Rank Tracker, Refresher, and the daily routine.

Google has no public "index this now" API for ordinary pages, so for Google the Indexer resubmits the sitemap and the
Rank Tracker watches each URL's index status; Bing takes URLs directly.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import time

import requests

from . import gsc, home, pipeline, research, settings, wp

log = logging.getLogger("seo_agent_team")
BING = "https://ssl.bing.com/webmaster/api.svc/json"


def site() -> str:
    return settings.SITE_URL.rstrip("/") + "/"


def _state_file():
    return home() / "team.json"


def load() -> dict:
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"index": {}, "refreshed": {}}


def save(s: dict) -> None:
    tmp = _state_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1), encoding="utf-8")
    tmp.replace(_state_file())


# --- Strategist -------------------------------------------------------------------------------------------------
def pick_topic() -> dict:
    topics = research.propose(wp.site_links(), n=5)
    used = research.used_keywords() | {p.get("keyword", "").lower() for p in pipeline.published()}
    for t in topics:
        t["title"] = re.sub(r"^\s*(working\s+)?title\s*\d*\s*[:\-–]\s*", "", t.get("title", ""), flags=re.I).strip() \
            or t["focus_keyword"].title()
        if t["focus_keyword"].lower().strip() not in used:
            log.info("Strategist picked \"%s\" (keyword: %s). Why: %s", t["title"], t["focus_keyword"], t.get("why", ""))
            return t
    raise RuntimeError("every suggested keyword is already used: add more SEO_SEEDS")


# --- Writer + Editor --------------------------------------------------------------------------------------------
def write_next(topic: dict | None = None) -> str:
    topic = topic or pick_topic()
    state = pipeline.write(topic, progress=log.info)
    chk = state["check"]
    if state.get("status") == "published":
        return f"Published \"{state['article']['title']}\" (Rank Math {chk['score']}/100): {state.get('link')}"
    return f"\"{state['article']['title']}\" scored {chk['score']}/100, under {settings.TARGET}: held for a human."


# --- Indexer ----------------------------------------------------------------------------------------------------
def submit(url: str) -> dict:
    """Tell Bing (and IndexNow partners) about one page, and resubmit the sitemap to Google."""
    out = {"t": time.time(), "bing": "not set up (SEO_BING_KEY)", "google": "not set up (Search Console)"}
    if settings.BING_KEY:
        try:
            r = requests.post(f"{BING}/SubmitUrlbatch", params={"apikey": settings.BING_KEY}, timeout=30,
                              json={"siteUrl": site(), "urlList": [url]})
            out["bing"] = "submitted" if r.ok else f"refused ({r.status_code}: {r.text[:80]})"
        except requests.RequestException as e:
            out["bing"] = f"failed ({type(e).__name__})"
    if gsc.ready():
        try:
            gsc.submit_sitemap()
            out["google"] = "sitemap resubmitted"
        except Exception as e:  # noqa: BLE001
            out["google"] = f"refused ({str(e)[:90]})"
    s = load()
    s.setdefault("index", {})[url] = {**s["index"].get(url, {}), **out}
    save(s)
    log.info("Indexer: %s -> Bing %s, Google %s", url, out["bing"], out["google"])
    return out


# --- Rank Tracker -----------------------------------------------------------------------------------------------
def _bing_pages() -> dict:
    r = requests.get(f"{BING}/GetPageStats", params={"apikey": settings.BING_KEY, "siteUrl": site()}, timeout=30)
    r.raise_for_status()
    out: dict = {}
    for row in (r.json() or {}).get("d") or []:
        u = row.get("Query") or row.get("Url") or ""
        o = out.setdefault(u.rstrip("/") + "/", {"impressions": 0, "clicks": 0, "pos_sum": 0.0})
        imp = int(row.get("Impressions") or 0)
        o["impressions"] += imp
        o["clicks"] += int(row.get("Clicks") or 0)
        o["pos_sum"] += float(row.get("AvgImpressionPosition") or 0) * imp
    for o in out.values():
        o["position"] = round(o.pop("pos_sum") / o["impressions"], 1) if o["impressions"] else None
    return out


def _track_file():
    return home() / "tracking.json"


def tracking() -> dict:
    try:
        return json.loads(_track_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"articles": [], "trend": [], "errors": []}


def track() -> dict:
    """Per-article Google and Bing numbers, top searches, index status, and the site's 90-day trend."""
    arts = pipeline.published()
    t: dict = {"t": time.time(), "google": gsc.ready(), "bing": bool(settings.BING_KEY), "articles": [],
               "trend": [], "errors": []}
    prev = {a["url"]: a for a in tracking().get("articles", [])}
    pages, queries, bing = {}, {}, {}
    if gsc.ready():
        try:
            for r in gsc.rows(["page"], 28):
                pages[r["keys"][0]] = {"impressions": int(r["impressions"]), "clicks": int(r["clicks"]),
                                       "ctr": round(r["ctr"], 4), "position": round(r["position"], 1)}
            for r in gsc.rows(["page", "query"], 28, 5000):
                queries.setdefault(r["keys"][0], []).append(
                    {"query": r["keys"][1], "impressions": int(r["impressions"]), "clicks": int(r["clicks"]),
                     "position": round(r["position"], 1)})
            t["trend"] = [{"date": r["keys"][0], "impressions": int(r["impressions"]), "clicks": int(r["clicks"]),
                           "position": round(r["position"], 1)} for r in gsc.rows(["date"], 90)]
        except Exception as e:  # noqa: BLE001
            t["errors"].append(f"Search Console: {str(e)[:120]}")
    if settings.BING_KEY:
        try:
            bing = _bing_pages()
        except Exception as e:  # noqa: BLE001
            t["errors"].append(f"Bing: {str(e)[:120]}")
    s = load()
    for a in arts:
        url = a["url"]
        old = prev.get(url) or {}
        row = {"title": a["title"], "url": url, "keyword": a.get("keyword", ""), "published": a.get("t", ""),
               "google": pages.get(url) or pages.get(url.rstrip("/")) or {}, "bing": bing.get(url) or {},
               "queries": sorted(queries.get(url, []), key=lambda q: -q["impressions"])[:8],
               "indexed": old.get("indexed"), "index_checked": old.get("index_checked", 0),
               "submitted": (s.get("index") or {}).get(url, {}), "refreshed": (s.get("refreshed") or {}).get(url)}
        if gsc.ready() and time.time() - (row["index_checked"] or 0) > 3 * 86400:   # the inspection quota is small
            try:
                ins = gsc.inspect(url)
                row["indexed"] = {"verdict": ins["verdict"], "state": ins["state"], "last_crawl": ins["last_crawl"]}
                row["index_checked"] = time.time()
            except Exception as e:  # noqa: BLE001
                t["errors"].append(f"URL inspection: {str(e)[:100]}")
        t["articles"].append(row)
    _track_file().write_text(json.dumps(t, indent=1), encoding="utf-8")
    return t


def summary(t: dict | None = None) -> str:
    t = t or tracking()
    arts = t.get("articles", [])
    gi = sum((a.get("google") or {}).get("impressions", 0) for a in arts)
    gc = sum((a.get("google") or {}).get("clicks", 0) for a in arts)
    lines = [f"{len(arts)} articles · Google (28 days): {gi:,} impressions, {gc:,} clicks"]
    for a in sorted(arts, key=lambda a: -(a.get("google") or {}).get("impressions", 0))[:10]:
        g = a.get("google") or {}
        lines.append(f"- {a['title']}: {g.get('impressions', 0):,} impressions, position {g.get('position', '-')}")
    return "\n".join(lines + [f"! {e}" for e in t.get("errors", [])])


# --- Refresher ----------------------------------------------------------------------------------------------------
def pick_refresh(t: dict, s: dict, now: float | None = None) -> dict | None:
    """The article with the best chance of moving up: 3+ weeks old, seen on Google (30+ impressions) but sitting
    around page 2-3 (position 8-30), and not refreshed in the last 45 days."""
    now = now or time.time()
    best = None
    for a in t.get("articles", []):
        g = a.get("google") or {}
        try:
            age = now - dt.datetime.fromisoformat(a["published"]).timestamp()
        except (ValueError, TypeError):
            age = 0
        last = (s.get("refreshed") or {}).get(a["url"], 0)
        if age > 21 * 86400 and now - last > 45 * 86400 and g.get("impressions", 0) >= 30 \
                and 8 <= (g.get("position") or 0) <= 30:
            if not best or g["impressions"] > best["google"]["impressions"]:
                best = a
    return best


def refresh_one() -> str:
    best = pick_refresh(tracking(), load())
    if not best:
        return "Nothing to refresh yet (needs Google data: 30+ impressions at position 8-30)."
    qs = ", ".join(f"\"{q['query']}\" (position {q['position']})" for q in best.get("queries", [])[:6])
    instruction = (f"Refresh this article so it ranks higher. People already find it on Google with these searches: "
                   f"{qs or best['keyword']}. Keep the same focus keyword and address. Answer those searches directly "
                   f"(add a short section or FAQ where it helps), bring facts and the year up to date for "
                   f"{dt.date.today().year}, tighten anything vague, and keep every claim accurate.")
    state = pipeline.refresh(best["url"], instruction)
    if not state:
        return f"The rewrite of \"{best['title']}\" scored under {settings.TARGET}: the live article was left unchanged."
    s = load()
    s.setdefault("refreshed", {})[best["url"]] = time.time()
    save(s)
    submit(best["url"])
    return f"Refreshed \"{best['title']}\" (Rank Math {state['check']['score']}/100)."


# --- the daily routine ----------------------------------------------------------------------------------------------
def run(today: dt.date | None = None) -> list[str]:
    """Run once a day (cron or Task Scheduler): track every day, write on SEO_WRITE_DAYS, refresh on SEO_REFRESH_DAY.
    One failing job never stops the others."""
    day = (today or dt.date.today()).strftime("%a").lower()
    jobs = [("track", lambda: summary(track()))]
    if day in settings.WRITE_DAYS:
        jobs.append(("write", write_next))
    if day == settings.REFRESH_DAY:
        jobs.append(("refresh", refresh_one))
    out = []
    for name, fn in jobs:
        try:
            out.append(f"[{name}] {fn()}")
        except Exception as e:  # noqa: BLE001
            log.exception("%s failed", name)
            out.append(f"[{name}] failed: {str(e).splitlines()[0][:200]}")
    return out
