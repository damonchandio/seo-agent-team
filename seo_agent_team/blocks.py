"""Markdown article -> WordPress block code (Gutenberg), with Rank Math's TOC and FAQ blocks."""
import html
import json
import re
import time


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:70]


def inline(s: str) -> str:
    out, pos = [], 0
    for m in re.finditer(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", s):
        out.append(_fmt(s[pos:m.start()]))
        out.append(f'<a href="{html.escape(m.group(2), quote=True)}">{_fmt(m.group(1))}</a>')
        pos = m.end()
    out.append(_fmt(s[pos:]))
    return "".join(out)


def _fmt(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)


def jattr(obj) -> str:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return (s.replace("--", "\\u002d\\u002d").replace("<", "\\u003c").replace(">", "\\u003e")
             .replace("&", "\\u0026"))


def para(t):
    return f"<!-- wp:paragraph -->\n<p>{inline(t)}</p>\n<!-- /wp:paragraph -->"


def heading(t, level, anchor):
    attrs = f' {{"level":{level}}}' if level != 2 else ""
    return (f"<!-- wp:heading{attrs} -->\n<h{level} class=\"wp-block-heading\" id=\"{anchor}\">{inline(t)}</h{level}>\n"
            f"<!-- /wp:heading -->")


def lst(items, ordered):
    tag = "ol" if ordered else "ul"
    head = '<!-- wp:list {"ordered":true} -->' if ordered else "<!-- wp:list -->"
    lis = "".join(f"<!-- wp:list-item -->\n<li>{inline(i)}</li>\n<!-- /wp:list-item -->" for i in items)
    return f'{head}\n<{tag} class="wp-block-list">{lis}</{tag}>\n<!-- /wp:list -->'


def table(rows):
    head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
    return ('<!-- wp:table -->\n<figure class="wp-block-table"><table class="has-fixed-layout"><thead><tr>'
            f"{head}</tr></thead><tbody>{body}</tbody></table></figure>\n<!-- /wp:table -->")


def image(img: dict, caption: str):
    return (f'<!-- wp:image {{"id":{img["id"]},"sizeSlug":"full","linkDestination":"none"}} -->\n'
            f'<figure class="wp-block-image size-full"><img src="{html.escape(img["url"], quote=True)}" '
            f'alt="{html.escape(img["alt"], quote=True)}" class="wp-image-{img["id"]}"/>'
            f'<figcaption class="wp-element-caption">{inline(caption)}</figcaption></figure>\n<!-- /wp:image -->')


def toc(heads):
    """Rank Math's TOC block, saved the way its editor saves it (the front end shows this HTML)."""
    hs = [{"key": f"toc-{i}", "content": _fmt(t), "level": lvl, "link": f"#{a}",
           "disable": False, "isUpdated": False, "isGeneratedLink": True} for i, (t, lvl, a) in enumerate(heads)]
    items = "".join(f'<li class=""><a href="#{a}">{_fmt(t)}</a></li>' for t, _, a in heads)
    attrs = {"title": "Table of Contents", "headings": hs, "listStyle": "ul", "titleWrapper": "h2"}
    return (f"<!-- wp:rank-math/toc-block {jattr(attrs)} -->\n"
            f'<div class="wp-block-rank-math-toc-block" id="rank-math-toc"><h2>Table of Contents</h2><nav><ul>{items}'
            f"</ul></nav></div>\n<!-- /wp:rank-math/toc-block -->")


def faq(qas):
    """Rank Math's FAQ block. The live page is built from the attributes, so they hold the HTML."""
    stamp = int(time.time() * 1000)
    qs = [{"id": f"faq-question-{stamp + i}", "title": inline(q), "content": inline(a), "visible": True}
          for i, (q, a) in enumerate(qas)]
    items = "".join(f'<div class="rank-math-faq-item"><h3 class="rank-math-question">'
                    f'{inline(q)}</h3><div class="rank-math-answer">{inline(a)}</div></div>'
                    for q, a in qas)
    return (f"<!-- wp:rank-math/faq-block {jattr({'questions': qs, 'titleWrapper': 'h3'})} -->\n"
            f'<div class="wp-block-rank-math-faq-block">{items}</div>\n<!-- /wp:rank-math/faq-block -->')


def convert(md: str, images: dict[int, dict]) -> str:
    """images: {n: {"id", "url", "alt"}} already uploaded to WordPress."""
    chunks = []
    for c in (c.strip() for c in md.split("\n\n")):
        if c.startswith("#") and "\n" in c:  # a heading with no blank line after it
            first, rest = c.split("\n", 1)
            chunks += [first.strip(), rest.strip()]
        elif c:
            chunks.append(c)
    heads, used, order = [], set(), []
    for c in chunks:
        m = re.match(r"^(#{2,3}) (.+)$", c)
        if m:
            a = slugify(m.group(2))
            while a in used:
                a += "-2"
            used.add(a)
            order.append(a)
            if not m.group(2).lower().startswith("frequently asked"):
                heads.append((m.group(2).strip(), len(m.group(1)), a))
    anchor_iter = iter(order)
    blocks, qas, in_faq, i = [], [], False, 0
    while i < len(chunks):
        c = chunks[i]
        if in_faq:
            if c.startswith("### ") and i + 1 < len(chunks):
                qas.append((c[4:].strip(), chunks[i + 1].strip()))
                i += 2
                continue
            blocks.append(faq(qas))
            in_faq, qas = False, []
        m = re.fullmatch(r"\[IMAGE (\d+): (.+)\]", c)
        if c == "[TOC]":
            blocks.append(toc([h for h in heads if h[1] == 2]))
        elif m:
            img = images.get(int(m.group(1)))
            if img:
                blocks.append(image(img, m.group(2)))
        elif c.startswith("## "):
            t = c[3:].strip()
            blocks.append(heading(t, 2, next(anchor_iter, slugify(t))))
            if t.lower().startswith("frequently asked"):
                in_faq = True
        elif c.startswith("### "):
            t = c[4:].strip()
            blocks.append(heading(t, 3, next(anchor_iter, slugify(t))))
        elif c.startswith("|"):
            rows = [[x.strip() for x in r.strip().strip("|").split("|")] for r in c.splitlines()
                    if r.strip() and not re.match(r"^\|?[\s:|-]+\|?$", r.strip())]
            if rows:
                blocks.append(table(rows))
        elif all(re.match(r"^[-*] ", l) for l in c.splitlines()):
            blocks.append(lst([l[2:].strip() for l in c.splitlines()], False))
        elif all(re.match(r"^\d+\. ", l) for l in c.splitlines()):
            blocks.append(lst([re.sub(r"^\d+\. ", "", l).strip() for l in c.splitlines()], True))
        else:
            blocks.append(para(" ".join(l.strip() for l in c.splitlines())))
        i += 1
    if in_faq and qas:
        blocks.append(faq(qas))
    return "\n\n".join(blocks) + "\n"


def preview_html(a: dict, content: str, embed: dict | None = None, featured: str = "") -> str:
    """A phone-friendly HTML preview of the post. embed maps image URLs to
    data: URIs so the pictures show even where the phone won't load web images inside a file."""
    for url, data in (embed or {}).items():
        content = content.replace(f'src="{url}"', f'src="{data}"')
    body = re.sub(r"<!-- /?wp:[^>]*-->", "", content)
    meta = (f"<div class=meta><b>SEO title:</b> {html.escape(a['seo_title'])}<br><b>Meta:</b> {html.escape(a['meta'])}"
            f"<br><b>Focus keyword:</b> {html.escape(a['focus_keyword'])} · <b>Slug:</b> /{html.escape(a['slug'])}/</div>")
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(a['title'])}</title><style>body{{font:17px/1.6 -apple-system,Segoe UI,sans-serif;"
            f"max-width:720px;margin:0 auto;padding:16px;color:#0f1e2e}}img{{max-width:100%;border-radius:8px}}"
            f"table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #ccd;padding:6px}}"
            f".meta{{background:#eef6fc;padding:12px;border-radius:8px;font-size:14px}}a{{color:#0e6fa3}}"
            f"figcaption{{font-size:13px;color:#567}}</style><div class=meta style='background:#fff4d6'>DRAFT for "
            f"approval</div>{meta}<h1>{html.escape(a['title'])}</h1>"
            + (f'<img src="{featured}" alt="featured image">' if featured else "") + body)
