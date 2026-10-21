"""The Writer: drafts an article, repairs failed Rank Math checks, and makes a human's requested edits.

The only things it may say about your business come from business_facts.md in the data folder (created from a
template on first run: fill it in). Everything else must come from the sourced facts research found.
"""
import json
import logging
import re

from . import home, settings
from .llm import call, parse_json

log = logging.getLogger("seo_agent_team")
SPLIT = "=====ARTICLE====="

DEFAULT_FACTS = """# Facts the writer may use about your business (edit this file)
- What you do, in one or two sentences.
- Where you work (town, region, remote).
- Who runs it and why they know the subject.
- How you work with customers (free call, fixed quotes, what's included).
- Contact page: https://example.com/contact/
"""


def business_facts() -> str:
    f = home() / "business_facts.md"
    if not f.exists():
        f.write_text(DEFAULT_FACTS, encoding="utf-8")
        log.warning("wrote a template %s: fill it in so articles describe your business correctly", f)
    return f.read_text(encoding="utf-8")


def style() -> str:
    return f"""House style (follow exactly):
- {settings.COUNTRY_NAME} English, plain words, short sentences. Write for busy {settings.AUDIENCE}.
- No em dashes or en dashes anywhere. Use commas, full stops or "to".
- No hype ("revolutionise", "game-changer", "unlock", "harness", "delve", "landscape", "seamless", "cutting-edge").
- Every paragraph under 100 words. Most are 2-4 sentences.
- Never invent statistics, surveys, prices from other companies, quotes or client stories. Use only the facts
  provided (and link them), the business facts, or clearly labelled round-number examples ("for example").
- Honest: say when the product or service is not the answer."""


def rules() -> str:
    return f"""Rank Math rules (the article must pass all of them):
- Focus keyword: use it exactly as given (same words, same order).
- SEO title: starts with the focus keyword, 50-60 characters, contains a number, a power word (Proven, Essential,
  Complete, Simple, Practical, Honest) and a sentiment word (Best, Proven, Mistakes, Avoid, Easy, Honest).
- Meta description: 140-158 characters, contains the focus keyword near the start.
- Slug: the focus keyword in lowercase with hyphens, plus at most 2 more words. Under 50 characters.
- Body: 2,600 to 2,900 words.
- The focus keyword appears in the first sentence, and in total 1.0% to 1.3% of words (about 1 use per 85 words,
  so roughly 28-34 uses in 2,700 words). Use it naturally, never twice in one sentence.
- At least 3 H2 headings contain the focus keyword. 7-10 H2 sections, H3s where useful.
- Right after the 2-3 paragraph introduction, a line containing only [TOC].
- Three image markers on their own lines, spread through the article: [IMAGE 1: caption], [IMAGE 2: caption],
  [IMAGE 3: caption]. Each caption is one sentence describing the image.
- Internal links: 3-6 links to the site pages provided, written as markdown links with natural anchor text.
- External links: link 2-4 of the provided facts to their source URLs. Never link anything else external.
- One markdown table where it helps (costs, comparison).
- Last two sections: a section about how {settings.BUSINESS_NAME} does this (from the business facts) ending with a
  bold call to action linking to the contact page, then "## Frequently Asked Questions" with 6-7 questions as
  "### Question?" each followed by a 2-3 sentence answer paragraph.
- Formatting: ## and ### headings, blank lines between blocks, "- " bullets, "1. " numbered lists, **bold**,
  [text](url) links. Nothing else (no HTML, no images other than the markers)."""


OUTPUT = f"""Write the answer straight away: don't plan or draft it at length first.
Output format, exactly:
```json
{{"title": "post title (can be longer, with the year)", "seo_title": "...", "meta": "...", "slug": "...",
 "excerpt": "one-sentence summary", "featured": {{"kicker": "SHORT LABEL", "headline": "2-5 word headline",
 "subhead": "one line"}},
 "images": [
  {{"n": 1, "alt": "alt text, the first one contains the focus keyword", "kind": "steps", "title": "...", "subtitle": "...",
    "items": [{{"label": "short", "text": "one sentence"}}]}},
  {{"n": 2, "alt": "...", "kind": "bars", "title": "...", "subtitle": "...", "unit": "£ or % or hrs",
    "items": [{{"label": "short", "value": 123}}]}},
  {{"n": 3, "alt": "...", "kind": "checklist", "title": "...", "subtitle": "...", "items": [{{"label": "short line"}}]}}
 ]}}
```
{SPLIT}
(the article in markdown, starting with the introduction, no H1)

Image kinds: "steps" (3-5 items), "bars" (3-6 items with numbers taken from the article; only real or clearly
example figures), "checklist" (4-7 items), "compare" (exactly 2 items, each {{"label": "...", "points": ["...", "..."]}})."""


def parse(text: str) -> dict:
    if SPLIT in text:
        head, md = text.split(SPLIT, 1)
    else:  # no divider: take the JSON block, and the article is whatever follows it
        m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
        if m and len(text[m.end():].split()) >= 300:
            head, md = m.group(1), text[m.end():]
        else:   # a bare JSON object first, then the article
            t = re.sub(r"^```(?:json)?\s*", "", text.strip())
            i = t.find("{")
            try:
                obj, end = json.JSONDecoder().raw_decode(t[i:]) if i >= 0 else (None, 0)
            except ValueError:
                obj, end = None, 0
            rest = re.sub(r"^\s*```\s*", "", t[i + end:]) if obj is not None else ""
            if not isinstance(obj, dict) or len(rest.split()) < 300:
                raise ValueError("the writer's reply was missing the article")
            head, md = json.dumps(obj), rest
    a = parse_json(head)
    a["markdown"] = re.sub(r"^```\w*\s*|\s*```$", "", md.strip()).strip()
    a["markdown"] = a["markdown"].replace("—", ", ").replace("–", " to ")
    a["alts"] = [i.get("alt", "") for i in a.get("images", [])]
    return a


def _context(topic: dict, facts: list[dict], links: list[dict]) -> str:
    host = re.sub(r"^https?://", "", settings.SITE_URL).strip("/")
    pages = "\n".join(f"- {l['title']}: {l['link']}" for l in links if host and host in l["link"])
    fx = "\n".join(f"- {f['fact']} (source: {f['source_name']}, {f['url']})" for f in facts) or "(none: avoid specific statistics)"
    return (f"Focus keyword: {topic['focus_keyword']}\nWorking title: {topic.get('title', '')}\n"
            f"Angle: {topic.get('angle', '')}\n\nBusiness facts:\n{business_facts()}\n\nSite pages for internal links:\n"
            f"{pages}\n\nSourced facts you may use and link:\n{fx}")


def draft(topic: dict, facts: list[dict], links: list[dict]) -> dict:
    system = (f"You write SEO articles for {settings.SITE_URL} that score 95+ in Rank Math and genuinely help the "
              "reader.\n\n" + style() + "\n\n" + rules() + "\n\n" + OUTPUT)
    a = parse(call(system, _context(topic, facts, links), max_tokens=32000))
    a["focus_keyword"] = topic["focus_keyword"]
    return a


def head(a: dict) -> str:
    keep = {k: a[k] for k in ("title", "seo_title", "meta", "slug", "excerpt", "featured", "images") if k in a}
    return "```json\n" + json.dumps(keep, indent=1, ensure_ascii=False) + "\n```\n" + SPLIT + "\n" + a["markdown"]


def fix(a: dict, hints: list[str], stats: dict) -> dict:
    """Targeted repair of the Rank Math tests that failed."""
    system = ("You repair an SEO article so it passes the failed Rank Math checks listed. Change as little as "
              "possible; keep the facts, links, markers, headings style and voice.\n\n" + style() + "\n\n" + rules()
              + "\n\n" + OUTPUT)
    user = (f"Focus keyword: {a['focus_keyword']}\nCurrent stats: {json.dumps(stats)}\nFix these:\n- "
            + "\n- ".join(hints) + "\n\nArticle:\n" + head(a))
    b = parse(call(system, user, max_tokens=32000, temperature=0.2))
    b["focus_keyword"] = a["focus_keyword"]
    return b


def revise(a: dict, instruction: str) -> dict:
    """A human's edit request, or the Refresher's rewrite brief."""
    system = ("You edit an SEO article exactly as the owner asks, keeping everything else, and keeping it passing "
              "these rules.\n\n" + style() + "\n\n" + rules() + "\n\n" + OUTPUT)
    user = f"Focus keyword: {a['focus_keyword']}\nThe owner's request: {instruction}\n\nArticle:\n" + head(a)
    b = parse(call(system, user, max_tokens=32000))
    b["focus_keyword"] = a["focus_keyword"]
    return b
