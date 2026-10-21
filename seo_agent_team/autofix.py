"""Helping free and open-source models reach Rank Math 95+.

Smaller models write well section by section but stop short of 2,500 words, and they're unreliable at mechanical
rules (keyword at the start of the title, in three headings, links, image markers, the [TOC] line). So:

  expand()      grows a short draft one section at a time (each call asks for ~350-450 words and the keyword a
                few times), never inventing statistics, prices or sources.
  mechanical()  fixes the rule-based checks exactly in code: title, meta, intro, headings, [TOC], internal links,
                one external source, image markers, long paragraphs.

Neither touches facts: expand() is told to keep every fact and link and add no new numbers; mechanical() only adds
the keyword, links to the site's own pages and to the sources the research found.
"""
from __future__ import annotations

import datetime as dt
import logging
import re

from . import rankmath, settings
from .llm import call

log = logging.getLogger("seo_agent_team")
TARGET_WORDS = 2700

EXPAND_SYSTEM = """You expand one section of a blog article for {site}, the website of {business}. Readers are
{audience}. Plain {country} English, practical, specific, no hype, no exclamation marks.

Rewrite the section so it is about {words} words. Keep its heading line exactly. Keep every fact, figure, link and
[IMAGE n: ...] marker that is already there. Add useful detail: how it works, steps, examples, what to watch out
for, questions to ask a supplier. Do NOT invent statistics, percentages, prices, dates, studies or sources.
Use the exact phrase "{kw}" {times} times, naturally. Short paragraphs (under 100 words). Return only the section
in Markdown, nothing else."""


def _sections(md: str) -> list[str]:
    """Split on H2 headings; the first item is the intro (text before the first H2)."""
    parts = re.split(r"(?m)^(?=## )", md)
    return [p for p in parts if p.strip()]


def expand(a: dict, progress=log.info) -> dict:
    kw = a["focus_keyword"]
    md = a["markdown"]
    n = len(rankmath.words(rankmath.plain(md)))
    if n >= TARGET_WORDS - 200:
        return a
    secs = _sections(md)
    body = [i for i, s in enumerate(secs) if s.startswith("## ") and not re.match(r"## (faq|frequently|conclusion|sources)", s, re.I)]
    if not body:
        return a
    need = TARGET_WORDS - n
    per = max(250, min(550, int((n + need) / max(1, len(body)))))
    times = max(2, round(per * 0.012 / max(1, len(kw.split())) * len(kw.split())))   # ~1.2% density per section
    for k, i in enumerate(body):
        progress(f"Expanding section {k + 1} of {len(body)} (draft is {n:,} words, target {TARGET_WORDS:,})")
        try:
            out = call(EXPAND_SYSTEM.format(words=per, kw=kw, times=times, site=settings.SITE_URL,
                                            business=settings.BUSINESS, audience=settings.AUDIENCE,
                                            country=settings.COUNTRY_NAME),
                       secs[i], max_tokens=1400, temperature=0.4)
        except Exception as e:  # noqa: BLE001
            log.warning("expanding a section failed: %s", e)
            continue
        out = re.sub(r"^```\w*\s*|\s*```$", "", out.strip()).strip()
        head = secs[i].splitlines()[0].strip()
        if not out.startswith("## "):
            out = head + "\n\n" + out
        old_markers = set(re.findall(r"\[IMAGE \d+:[^\]]*\]", secs[i]))
        for m in old_markers - set(re.findall(r"\[IMAGE \d+:[^\]]*\]", out)):
            out += "\n\n" + m                          # never lose an image marker
        if len(rankmath.words(rankmath.plain(out))) > len(rankmath.words(rankmath.plain(secs[i]))):
            secs[i] = out.replace("—", ", ").replace("–", " to ") + "\n\n"
    a["markdown"] = "".join(secs).strip()
    return a


ACRONYMS = {"ai", "uk", "us", "eu", "rag", "seo", "crm", "api", "gdpr", "llm", "nhs", "hmrc", "vat", "it", "erp", "pwa"}


def _cap(kw: str) -> str:
    """'ai chatbot cost uk' -> 'AI chatbot cost UK' (acronyms in capitals, first letter capital)."""
    ws = [w.upper() if w.lower() in ACRONYMS else w for w in kw.split()]
    out = " ".join(ws)
    return out[:1].upper() + out[1:]


def _split_long(md: str) -> str:
    out = []
    for p in md.split("\n\n"):
        if re.match(r"^(#|\||- |\d+\. |\[)", p.strip()) or len(rankmath.words(p)) <= 110:
            out.append(p)
            continue
        sents = re.split(r"(?<=[.!?])\s+", p.strip())
        cur = []
        for s in sents:
            cur.append(s)
            if len(rankmath.words(" ".join(cur))) >= 70:
                out.append(" ".join(cur))
                cur = []
        if cur:
            out.append(" ".join(cur))
    return "\n\n".join(out)


def mechanical(a: dict, site_links: list[dict] | None = None, facts: list[dict] | None = None) -> dict:
    kw, K = a["focus_keyword"].strip(), _cap(a["focus_keyword"].strip())
    kwl = kw.lower()
    year = dt.date.today().year
    site = re.sub(r"^https?://", "", settings.SITE_URL).strip("/")
    md = a["markdown"]
    # SEO title: keyword first, a number, a power + sentiment word ("honest" is both)
    t = a.get("seo_title") or a.get("title") or K
    tl = t.lower()
    if not tl.startswith(kwl) or not re.search(r"\d", t) or not any(w in rankmath.POWER for w in re.findall(r"[a-z\-]+", tl)) \
            or not any(w in rankmath.SENTIMENT for w in re.findall(r"[a-z\-]+", tl)):
        a["seo_title"] = f"{K}: The Honest {year} Guide"   # the year is the number; "honest" is power and sentiment
        if len(a["seo_title"]) > 60:
            a["seo_title"] = f"{K}: Honest {year} Guide"
    # meta description
    meta = (a.get("meta") or "").strip()
    if kwl not in meta.lower():
        meta = f"{K}: {meta}" if meta else f"{K} for {settings.AUDIENCE}: what it involves, what it costs and what to ask."
    a["meta"] = meta[:160]
    # intro: the keyword in the first tenth of the text
    words = rankmath.words(rankmath.plain(md))
    intro = " ".join(words[: max(1, len(words) // 10)]).lower()
    if kwl not in intro:
        parts = md.split("\n\n")
        for i, p in enumerate(parts):
            if p.strip() and not re.match(r"^(#|\[|\||- |\d+\. )", p.strip()):
                k = _cap(kw) if _cap(kw).split()[0].isupper() else _cap(kw)[:1].lower() + _cap(kw)[1:]
                parts[i] = f"This guide explains {k} in plain terms for {settings.AUDIENCE}. " + p
                break
        md = "\n\n".join(parts)
    # [TOC] after the first paragraph
    if "[TOC]" not in md:
        parts = md.split("\n\n")
        at = next((i for i, p in enumerate(parts) if p.strip() and not p.lstrip().startswith("#")), 0)
        parts.insert(at + 1, "[TOC]")
        md = "\n\n".join(parts)
    # three headings with the keyword
    heads = re.findall(r"(?m)^(#{2,3}) (.+)$", md)
    have = sum(1 for _, h in heads if kwl in h.lower())
    if have < 3:
        for lvl, h in heads:
            if have >= 3:
                break
            if kwl in h.lower() or re.match(r"(faq|frequently|sources|conclusion)", h, re.I):
                continue
            md = md.replace(f"{lvl} {h}", f"{lvl} {K}: {h[:1].lower() + h[1:]}", 1)
            have += 1
    # links
    links = re.findall(r"\[[^\]]+\]\((https?://[^)\s]+)\)", md)
    internal = {u for u in links if site in u}
    if len(internal) < 2 and site_links:
        pool = [l for l in site_links if l.get("link") and l["link"] not in internal
                and not re.search(r"privacy|cookie|terms|cart|checkout|account|sample", l["link"], re.I)]
        pool.sort(key=lambda l: l.get("kind") != "post")
        add = pool[: 2 - len(internal)]
        if add:
            md += "\n\nRelated reading: " + " and ".join(f"[{l['title']}]({l['link']})" for l in add) + "."
    if not [u for u in links if site not in u]:
        srcs = [f for f in (facts or []) if f.get("url")]
        if srcs:   # with no sourced facts there's no honest external link to add: the Editor will hold it back
            md += "\n\n## Sources\n\n" + "\n".join(f"- [{f.get('source_name') or f['url']}]({f['url']})" for f in srcs[:6])
    # image markers, spread through the article
    if not re.search(r"\[IMAGE \d+:", md) and a.get("images"):
        parts = re.split(r"(?m)^(?=## )", md)
        h2 = [i for i, p in enumerate(parts) if p.startswith("## ")
              and not re.match(r"## (faq|frequently|sources|conclusion|related)", p, re.I)]
        for k, img in enumerate(a["images"][:3]):
            if not h2:
                break
            i = h2[min(len(h2) - 1, (k + 1) * len(h2) // (len(a["images"][:3]) + 1))]
            parts[i] = parts[i].rstrip() + f"\n\n[IMAGE {img.get('n', k + 1)}: {img.get('alt') or img.get('title') or K}]\n\n"
        md = "".join(parts)
    # alt text with the keyword
    if a.get("images") and not any(kwl in (i.get("alt") or "").lower() for i in a["images"]):
        a["images"][0]["alt"] = f"{K}: {a['images'][0].get('alt', '')}".strip(": ")
    a["markdown"] = _split_long(md)
    a["alts"] = [i.get("alt", "") for i in a.get("images", [])]
    return a
