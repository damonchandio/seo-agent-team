"""One article, start to finish: research, draft, the Editor's Rank Math fixes, images, WordPress, and then either
live (95+) or held for a human.

The human step is a hook. By default a held draft is saved (JSON plus an HTML preview in seo-data/drafts/) and a
message is printed; publish it with `python -m seo_agent_team publish <slug>`. To be asked somewhere else (email,
Slack, Telegram), replace it:

    from seo_agent_team import pipeline
    pipeline.approve = lambda state: send_to_my_phone(state["article"]["title"], state["preview_file"])
"""
import base64
import copy
import datetime as dt
import io
import json
import logging
import re
import threading

from . import blocks, home, images, rankmath, research, settings, wp, writer
from .llm import call, parse_json

log = logging.getLogger("seo_agent_team")
_busy = threading.Lock()


def drafts():
    return home() / "drafts"


def _host() -> str:
    return re.sub(r"^https?://", "", settings.SITE_URL).strip("/")


def _slug(a: dict) -> str:
    kw = re.sub(r"[^a-z0-9]+", "-", a["focus_keyword"].lower()).strip("-")
    s = re.sub(r"[^a-z0-9-]+", "-", (a.get("slug") or "").lower()).strip("-")
    if kw not in s:
        s = kw + ("-" + s if s else "")
    parts = s.split("-")
    while len(f"https://{_host()}/{'-'.join(parts)}/") > 75 and len(parts) > len(kw.split("-")):
        parts.pop()
    return "-".join(parts)


def _clean_links(a: dict) -> dict:
    """Make site links absolute, and drop external links that don't open (keeps the words)."""
    base = settings.SITE_URL.rstrip("/")
    a["markdown"] = re.sub(r"\]\((/[^)\s]*)\)", lambda m: f"]({base}{m.group(1)})", a["markdown"])

    def keep(m):
        url = m.group(2)
        if _host() in url or research.link_ok(url):
            return m.group(0)
        log.info("dropping dead link %s", url)
        return m.group(1)
    a["markdown"] = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", keep, a["markdown"])
    return a


def _tidy(a: dict) -> dict:
    a["slug"] = _slug(a)
    a["meta"] = (a.get("meta") or "").strip()[:160]
    alts = [i.get("alt", "") for i in a.get("images", [])]
    if alts and not any(a["focus_keyword"].lower() in x.lower() for x in alts):
        a["images"][0]["alt"] = f"{a['focus_keyword'][0].upper()}{a['focus_keyword'][1:]}: {alts[0]}"
    a["alts"] = [i.get("alt", "") for i in a.get("images", [])]
    return a


def polish(a: dict, progress=log.info, links: list | None = None, facts: list | None = None) -> tuple[dict, dict]:
    """The Editor: grow a short draft, fix the mechanical rules in code, then up to five model fix passes, keeping
    the best-scoring version. Returns (article, check)."""
    from . import autofix
    if links is None:
        try:
            links = wp.site_links()
        except Exception:  # noqa: BLE001
            links = []
    a = autofix.mechanical(autofix.expand(a, progress), links, facts)
    a = _tidy(_clean_links(a))
    used = research.used_keywords()
    best = (a, rankmath.check(a, used, _host()))
    for _ in range(5):
        r = best[1]
        if r["score"] >= settings.TARGET and "length" not in r["failed"] and "density" not in r["failed"]:
            break
        progress(f"Rank Math check {r['score']}/100, fixing: {', '.join(r['failed'])}")
        fixable = [h for k, h in zip(r["failed"], r["hints"]) if k != "unique_kw"]
        try:
            if "length" in r["failed"]:      # grow it section by section instead of a whole rewrite
                b = autofix.expand(copy.deepcopy(best[0]), progress)
            else:
                b = writer.fix(best[0], fixable, r["stats"])
        except Exception as e:  # noqa: BLE001  a bad fix never loses the draft
            log.warning("fix pass failed: %s", e)
            continue
        b = _tidy(_clean_links(autofix.mechanical(b, links, facts)))
        rb = rankmath.check(b, used, _host())
        if rb["score"] >= r["score"]:
            best = (b, rb)
    return best


def passes(state: dict) -> bool:
    """The Editor's rule for going live without a human: score at or above the target, long enough, keyword density
    right, and the Rank Math boxes saved in WordPress."""
    chk = state["check"]
    return (settings.AUTO_PUBLISH and chk["score"] >= settings.TARGET and "length" not in chk["failed"]
            and "density" not in chk["failed"] and bool(state.get("rank_math_saved")))


def _render_and_upload(a: dict, old: dict | None = None) -> dict:
    folder = home() / "images" / a["slug"]
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    feat_alt = f"{a['focus_keyword'][0].upper()}{a['focus_keyword'][1:]} guide"
    if old and old.get("featured_spec") == a.get("featured") and old.get("featured"):
        out["featured"] = old["featured"]
    else:
        p = images.featured(a.get("featured") or {}, folder / f"{a['slug']}-featured.png")
        out["featured"] = wp.upload_image(p, feat_alt, a["title"])
    out["inline"] = {}
    old_specs = {str(i["n"]): i for i in (old or {}).get("images_spec", [])}
    for spec in a.get("images", []):
        n = str(spec["n"])
        prev = (old or {}).get("inline", {}).get(n)
        if prev and old_specs.get(n) == spec:
            out["inline"][n] = prev
            continue
        p = images.graphic(spec, folder / f"{a['slug']}-{n}.png")
        out["inline"][n] = wp.upload_image(p, spec.get("alt") or a["title"])
    out["featured_spec"], out["images_spec"] = a.get("featured"), a.get("images", [])
    return out


def _data_uri(path) -> str:
    """A small JPEG copy of an image, inlined, so the preview file shows pictures anywhere."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.thumbnail((1100, 1100))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=78, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return ""


def save_state(state: dict) -> None:
    (drafts() / f"{state['article']['slug']}.json").write_text(json.dumps(state, indent=1, ensure_ascii=False),
                                                                encoding="utf-8")


def load_state(slug: str) -> dict:
    return json.loads((drafts() / f"{slug}.json").read_text(encoding="utf-8"))


def upload(a: dict, check: dict, old: dict | None = None, status: str = "draft") -> dict:
    media = _render_and_upload(a, (old or {}).get("media"))
    content = blocks.convert(a["markdown"], {int(k): v for k, v in media["inline"].items()})
    post = wp.save_post(a["title"], content, a["slug"], a.get("excerpt", ""), featured=media["featured"]["id"],
                        post_id=(old or {}).get("post_id"), status=status)
    rm = wp.set_rank_math(post["id"], a["focus_keyword"], a["seo_title"], a["meta"])
    state = {"article": a, "check": check, "media": media, "post_id": post["id"], "rank_math_saved": rm,
             "updated": dt.datetime.now().isoformat(), "status": "published" if status == "publish" else "draft"}
    if status == "publish":
        state["link"] = post.get("link") or (old or {}).get("link")
    folder = home() / "images" / a["slug"]
    embed = {img["url"]: _data_uri(folder / f"{a['slug']}-{n}.png") for n, img in media["inline"].items()}
    prev = drafts() / f"{a['slug']}.html"
    prev.write_text(blocks.preview_html(a, content, {k: v for k, v in embed.items() if v},
                                        _data_uri(folder / f"{a['slug']}-featured.png")), encoding="utf-8")
    state["preview_file"] = str(prev)
    save_state(state)
    return state


def default_approve(state: dict) -> None:
    a, chk = state["article"], state["check"]
    print(f"\nHeld for a human: \"{a['title']}\" scored {chk['score']}/100 (target {settings.TARGET}).\n"
          f"Failed checks: {', '.join(chk['failed']) or 'Rank Math boxes not saved'}\n"
          f"Preview: {state.get('preview_file')}\nWordPress draft: {wp.edit_link(state['post_id'])}\n"
          f"Publish it with: python -m seo_agent_team publish {a['slug']}\n")


approve = default_approve   # replace with your own hook (see the module docstring)


def published_file():
    return home() / "published.json"


def published() -> list[dict]:
    try:
        return json.loads(published_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def go_live(state: dict) -> dict:
    a = state["article"]
    post = wp.publish(state["post_id"])
    research.mark_used(a["focus_keyword"])
    state["status"], state["link"] = "published", post["link"]
    save_state(state)
    pub = published()
    if not any(p.get("url") == post["link"] for p in pub):
        pub.append({"t": dt.datetime.now().isoformat(), "title": a["title"], "url": post["link"],
                    "keyword": a["focus_keyword"]})
        published_file().write_text(json.dumps(pub, indent=1), encoding="utf-8")
    from . import team
    team.submit(post["link"])     # the Indexer
    return state


def publish_draft(slug: str) -> str:
    """A human approved a held draft."""
    state = go_live(load_state(slug))
    return f"Published: {state['link']}"


def write(topic: dict, progress=log.info) -> dict:
    """Research -> draft -> Editor -> images -> WordPress draft -> live if it passes, else approve()."""
    if not _busy.acquire(blocking=False):
        raise RuntimeError("already writing an article")
    try:
        progress("Reading the site's pages for internal links...")
        links = wp.site_links()
        progress("Researching sources...")
        facts = research.facts(topic)
        progress(f"Writing ({len(facts)} sourced facts)...")
        a = writer.draft(topic, facts, links)
        a, chk = polish(a, progress, links, facts)
        progress(f"Rank Math check {chk['score']}/100. Drawing images and saving the draft...")
        state = upload(a, chk)
        if passes(state):
            go_live(state)
        else:
            approve(state)
        return state
    finally:
        _busy.release()


def topic_from_text(text: str) -> dict:
    """'write about X' -> an article brief."""
    system = (f"Turn the owner's request into an SEO article brief for {settings.SITE_URL} ({settings.BUSINESS}). "
              'Return only JSON: {"focus_keyword": "2-4 word phrase buyers search", "title": "working title with a '
              'number", "angle": "one sentence"}')
    return parse_json(call(system, text, max_tokens=300))


def refresh(url: str, instruction: str, progress=log.info) -> dict | None:
    """Rewrite a live article in place (same post, same address). Only saved if it still passes the Editor."""
    state = None
    for f in drafts().glob("*.json"):
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if st.get("link", "").rstrip("/") == url.rstrip("/"):
            state = st
            break
    if not state:
        raise RuntimeError(f"no saved article for {url} (only articles this tool wrote can be refreshed)")
    if not _busy.acquire(blocking=False):
        raise RuntimeError("already writing an article")
    try:
        a = state["article"]
        progress("Rewriting around the searches people use...")
        b, chk = polish(writer.revise(a, instruction), progress)
        b["slug"] = a["slug"]
        if not passes({"check": chk, "rank_math_saved": True}):
            return None
        progress(f"Rank Math {chk['score']}/100: updating the live page...")
        return upload(b, chk, old=state, status="publish")
    finally:
        _busy.release()
