"""WordPress REST API, signed in with an Application Password.

Rank Math's fields (focus keyword, SEO title, description) are set through Rank Math's own endpoint, the one its
editor panel uses.
"""
import logging
import mimetypes
import re
from pathlib import Path

import requests

from . import settings

log = logging.getLogger("seo_agent_team")


class WPError(RuntimeError):
    pass


def ready() -> bool:
    return bool(settings.SITE_URL and settings.WP_USER and settings.WP_APP_PASSWORD)


def _req(method: str, path: str, **kw):
    if not ready():
        raise WPError("WordPress isn't connected: set SEO_SITE_URL, SEO_WP_USER and SEO_WP_APP_PASSWORD")
    url = settings.SITE_URL.rstrip("/") + "/wp-json/" + path.lstrip("/")
    r = requests.request(method, url, auth=(settings.WP_USER, settings.WP_APP_PASSWORD), timeout=120,
                         headers={"User-Agent": "seo-agent-team/1.0", **kw.pop("headers", {})}, **kw)
    if r.status_code >= 400:
        raise WPError(f"WordPress said {r.status_code} on {path}: {r.text[:240]}")
    return r.json() if r.text else {}


def check() -> str:
    me = _req("GET", "wp/v2/users/me", params={"context": "edit"})
    caps = me.get("capabilities") or {}
    if not (caps.get("publish_posts") or "administrator" in (me.get("roles") or [])):
        return f"Signed in as {me.get('name')}, but that user can't publish posts."
    return f"Signed in to WordPress as {me.get('name')}."


def site_links() -> list[dict]:
    """Every published post and page: title + link (for internal links and to avoid repeats)."""
    out = []
    for kind in ("posts", "pages"):
        for page in range(1, 4):
            try:
                rows = _req("GET", f"wp/v2/{kind}", params={"per_page": 100, "page": page,
                                                           "_fields": "id,link,title,slug,status"})
            except WPError:
                break
            out += [{"kind": kind[:-1], "id": r["id"], "title": re.sub("<[^>]+>", "", r["title"]["rendered"]),
                     "link": r["link"], "slug": r["slug"]} for r in rows]
            if len(rows) < 100:
                break
    return out


def upload_image(path: Path, alt: str, title: str = "") -> dict:
    data = Path(path).read_bytes()
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    m = _req("POST", "wp/v2/media", data=data, headers={
        "Content-Type": mime, "Content-Disposition": f'attachment; filename="{Path(path).name}"'})
    _req("POST", f"wp/v2/media/{m['id']}", json={"alt_text": alt, "title": title or alt, "caption": ""})
    return {"id": m["id"], "url": m.get("source_url"), "alt": alt}


def save_post(title: str, content: str, slug: str, excerpt: str, featured: int | None = None,
              post_id: int | None = None, status: str = "draft") -> dict:
    body = {k: v for k, v in {"title": title, "content": content, "slug": slug, "excerpt": excerpt,
                              "status": status}.items() if v is not None}
    if featured:
        body["featured_media"] = featured
    p = _req("POST", f"wp/v2/posts/{post_id}" if post_id else "wp/v2/posts", json=body)
    return {"id": p["id"], "link": p.get("link"), "status": p.get("status")}


def set_rank_math(post_id: int, focus: str, seo_title: str, description: str) -> bool:
    meta = {"rank_math_focus_keyword": focus, "rank_math_title": seo_title, "rank_math_description": description}
    try:
        _req("POST", "rankmath/v1/updateMeta", json={"objectType": "post", "objectID": post_id, "meta": meta})
        return True
    except WPError as e:
        log.warning("Rank Math meta via its endpoint failed (%s); trying post meta", e)
    try:  # works if the fields are exposed to the REST API (WordPress ignores them otherwise)
        p = _req("POST", f"wp/v2/posts/{post_id}", json={"meta": meta})
        return (p.get("meta") or {}).get("rank_math_focus_keyword") == focus
    except WPError as e:
        log.warning("Rank Math meta not saved: %s", e)
        return False


def publish(post_id: int) -> dict:
    p = _req("POST", f"wp/v2/posts/{post_id}", json={"status": "publish"})
    return {"id": p["id"], "link": p.get("link"), "status": p.get("status")}


def preview_link(post_id: int) -> str:
    return f"{settings.SITE_URL.rstrip('/')}/?p={post_id}&preview=true"


def edit_link(post_id: int) -> str:
    return f"{settings.SITE_URL.rstrip('/')}/wp-admin/post.php?post={post_id}&action=edit"
