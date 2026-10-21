"""Rank Math's content tests, run locally so a draft is fixed before it reaches WordPress.

Mirrors the checks in Rank Math's editor panel (free version): Basic SEO, Additional, Title
readability and Content readability. Weights are approximate; passing everything is 100 and the
target is 95+. Rank Math recalculates its own score when the post is opened in the editor.
"""
import re

POWER = {"proven", "ultimate", "essential", "complete", "simple", "easy", "free", "best", "powerful", "smart",
         "secret", "honest", "practical", "quick", "fast", "guaranteed", "instant", "effortless", "surprising",
         "remarkable", "breakthrough", "critical", "vital", "crucial", "expert", "insider", "definitive",
         "step-by-step", "costly", "mistakes", "avoid", "hidden", "real", "brilliant", "affordable", "cheap"}
SENTIMENT = {"best", "proven", "easy", "free", "amazing", "brilliant", "great", "honest", "worst", "mistakes",
             "avoid", "wrong", "fail", "failing", "costly", "hidden", "danger", "risky", "pitfalls", "simple",
             "smart", "win", "winning", "success", "successful", "affordable", "cheap", "powerful", "surprising"}
WEIGHTS = {"kw_in_title": 8, "kw_in_meta": 6, "kw_in_url": 6, "kw_in_intro": 6, "kw_in_content": 6, "length": 8,
           "kw_in_subheads": 6, "kw_in_alt": 5, "density": 8, "url_length": 3, "external": 4, "dofollow": 3,
           "internal": 4, "unique_kw": 5, "kw_title_start": 4, "sentiment": 2, "power": 3, "number": 3, "toc": 4,
           "short_paragraphs": 3, "media": 3}
HINTS = {
    "kw_in_title": "Put the focus keyword in the SEO title.",
    "kw_in_meta": "Put the focus keyword in the meta description.",
    "kw_in_url": "Put the focus keyword in the slug.",
    "kw_in_intro": "Use the focus keyword in the first two or three sentences.",
    "kw_in_content": "Use the focus keyword in the article body.",
    "length": "Make the article at least 2,500 words.",
    "kw_in_subheads": "Use the focus keyword in at least three H2 or H3 headings.",
    "kw_in_alt": "Use the focus keyword in an image's alt text.",
    "density": "Keyword density must be between 1.0% and 1.5%.",
    "url_length": "Shorten the slug.",
    "external": "Link to at least one external source.",
    "dofollow": "Make at least one external link a normal (dofollow) link.",
    "internal": "Link to at least two pages on your own site.",
    "unique_kw": "That focus keyword was used before: choose a different one.",
    "kw_title_start": "Start the SEO title with the focus keyword.",
    "sentiment": "Add a positive or negative sentiment word to the SEO title (best, proven, mistakes, honest...).",
    "power": "Add a power word to the SEO title (proven, essential, complete, simple...).",
    "number": "Put a number in the SEO title.",
    "toc": "Add [TOC] after the introduction.",
    "short_paragraphs": "Split every paragraph over 120 words.",
    "media": "Add images to the content.",
}


def plain(md: str) -> str:
    t = re.sub(r"\[IMAGE \d+: ([^\]]*)\]", r"\1", md).replace("[TOC]", "")
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[#*|>`]", " ", t)
    return re.sub(r"-{3,}", " ", t)


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z0-9£$%'’.,+\-]+", text) if re.search(r"[A-Za-z0-9]", w)]


def count_kw(text: str, kw: str) -> int:
    return len(re.findall(r"(?<![\w-])" + re.escape(kw) + r"(?![\w-])", text, flags=re.I))


def check(a: dict, used_keywords: set[str] | None = None, site: str = "example.com") -> dict:
    """a: {focus_keyword, seo_title, meta, slug, markdown, alts: [...]} -> {score, passed, failed, stats}"""
    kw = a["focus_keyword"].strip()
    kwl, md = kw.lower(), a["markdown"]
    body = plain(md)
    ws = words(body)
    n = len(ws)
    heads = re.findall(r"^#{2,4} (.+)$", md, flags=re.M)
    toc_heads = [h for h in re.findall(r"^## (.+)$", md, flags=re.M)] if "[TOC]" in md else []
    kw_n = count_kw(body, kw) + sum(count_kw(h, kw) for h in toc_heads)
    density = 100 * kw_n / max(n, 1)
    intro = " ".join(ws[: max(1, n // 10)])
    links = re.findall(r"\[[^\]]+\]\((https?://[^)\s]+)\)", md)
    internal = [u for u in links if site in u]
    external = [u for u in links if site not in u]
    paras = [p for p in md.split("\n\n") if p.strip() and not re.match(r"^(#|\||- |\d+\. |\[)", p.strip())]
    long_paras = [len(words(p)) for p in paras if len(words(p)) > 120]
    title = a.get("seo_title", "")
    tw = re.findall(r"[a-z\-]+", title.lower())
    slug = a.get("slug", "")
    kw_slug = re.sub(r"[^a-z0-9]+", "-", kwl).strip("-")
    tests = {
        "kw_in_title": kwl in title.lower(),
        "kw_in_meta": kwl in a.get("meta", "").lower(),
        "kw_in_url": kw_slug in slug,
        "kw_in_intro": kwl in intro.lower(),
        "kw_in_content": kw_n > 0,
        "length": n >= 2500,
        "kw_in_subheads": sum(1 for h in heads if kwl in h.lower()) >= 3,
        "kw_in_alt": any(kwl in (alt or "").lower() for alt in a.get("alts", [])),
        "density": 1.0 <= density <= 1.5,
        "url_length": len(f"https://{site}/{slug}/") <= 75,
        "external": bool(external),
        "dofollow": bool(external),
        "internal": len(set(internal)) >= 2,
        "unique_kw": kwl not in (used_keywords or set()),
        "kw_title_start": title.lower().find(kwl) == 0 or kwl in title.lower()[: len(title) // 2],
        "sentiment": any(w in SENTIMENT for w in tw),
        "power": any(w in POWER for w in tw),
        "number": bool(re.search(r"\d", title)),
        "toc": "[TOC]" in md,
        "short_paragraphs": not long_paras,
        "media": bool(re.search(r"\[IMAGE \d+:", md)),
    }
    score = sum(WEIGHTS[k] for k, ok in tests.items() if ok)
    failed = [k for k, ok in tests.items() if not ok]
    return {"score": score, "failed": failed, "hints": [HINTS[k] for k in failed],
            "stats": {"words": n, "keyword_uses": kw_n, "density": round(density, 2), "long_paragraphs": long_paras,
                      "internal_links": len(set(internal)), "external_links": len(external),
                      "keyword_headings": sum(1 for h in heads if kwl in h.lower())}}
