# -*- coding: utf-8 -*-
"""SEO and web publishing tools."""

from __future__ import annotations

import html as html_lib
import json
import re
import urllib.parse

from .common import ok, split_pipe, temp_path
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


def _escape(value: str) -> str:
    return html_lib.escape(value or "", quote=True)


# --------------------------------------------------------------------------
# JSON-LD
# --------------------------------------------------------------------------

def _json_ld_script(data) -> str:
    return '<script type="application/ld+json">\n' + json.dumps(data, ensure_ascii=False, indent=2) + "\n</script>"


def json_ld_generator(item: Input) -> Output:
    raw = item.require_text().strip()
    if raw.startswith("{") or raw.startswith("["):
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise ToolError(f"Invalid JSON: {exc}") from exc
        return ok(_json_ld_script(data), title="JSON-LD Generator")
    parts = raw.split("|")
    schema = parts[0].strip().lower() if parts else "article"
    data: dict = {"@context": "https://schema.org"}
    if schema == "product":
        name, brand, price, currency, description = (parts[1:6] + [""] * 5)[:5]
        data.update({"@type": "Product", "name": name})
        if brand:
            data["brand"] = {"@type": "Brand", "name": brand}
        if price:
            data["offers"] = {"@type": "Offer", "price": price, "priceCurrency": currency or "IRR"}
        if description:
            data["description"] = description
    elif schema == "organization":
        name, url, logo = (parts[1:4] + [""] * 3)[:3]
        data.update({"@type": "Organization", "name": name})
        if url:
            data["url"] = url
        if logo:
            data["logo"] = logo
    elif schema == "faq":
        pairs = []
        for line in (parts[1] if len(parts) > 1 else "").split(";"):
            if "|" in line:
                question, answer = line.split("|", 1)
                pairs.append(
                    {
                        "@type": "Question",
                        "name": question.strip(),
                        "acceptedAnswer": {"@type": "Answer", "text": answer.strip()},
                    }
                )
        data.update({"@type": "FAQPage", "mainEntity": pairs})
    elif schema == "breadcrumb":
        items = []
        for index, line in enumerate((parts[1] if len(parts) > 1 else "").split(";")):
            if "|" in line:
                name, url = line.split("|", 1)
                entry = {"@type": "ListItem", "position": index + 1, "name": name.strip()}
                if url.strip():
                    entry["item"] = url.strip()
                items.append(entry)
        data.update({"@type": "BreadcrumbList", "itemListElement": items})
    else:
        headline, author, date_published, image = (parts[1:5] + [""] * 4)[:4]
        data.update({"@type": "Article", "headline": headline})
        if author:
            data["author"] = {"@type": "Person", "name": author}
        if date_published:
            data["datePublished"] = date_published
        if image:
            data["image"] = image
    return ok(_json_ld_script(data), title="JSON-LD Generator")


_register(make_tool("json-ld-generator", json_ld_generator, title="JSON-LD Generator", hint="schema|fields or JSON"))


# --------------------------------------------------------------------------
# Keyword density
# --------------------------------------------------------------------------

_STOP = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "her",
    "was", "one", "our", "out", "has", "had", "his", "she", "him", "with", "this",
    "that", "from", "they", "your", "have", "will", "what", "when", "into",
    "of", "in", "on", "at", "to", "is", "it", "as", "or", "be", "by", "an", "a",
    "و", "در", "به", "از", "که", "این", "را", "با", "برای", "است", "آن", "یک",
    "های", "ها", "می", "شد", "شده", "بود", "هم", "یا", "بر", "تا", "کن", "کرد",
}


def keyword_density(item: Input) -> Output:
    words = [word.lower() for word in re.findall(r"[\w\u0600-\u06FF]+", item.require_text())]
    words = [word for word in words if len(word) >= 3 and word not in _STOP]
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    rows = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:50]
    total = len(words)
    lines = [f"Words: {total}  Unique: {len(counts)}", ""]
    for word, count in rows:
        lines.append(f"{count:>4}  {count / total * 100:5.1f}%  {word}")
    return ok("\n".join(lines), title="Keyword Density")


_register(make_tool("keyword-density", keyword_density, title="Keyword Density", hint="clipboard text"))


# --------------------------------------------------------------------------
# Meta tags
# --------------------------------------------------------------------------

def meta_tag_generator(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 9, from_right=False, strip=False)
    title, description, keywords, author, og_title, og_description, og_image, og_url, twitter_card = parts
    lines = []
    if title.strip():
        lines.append(f"<title>{_escape(title.strip())}</title>")
    for name, value in [("description", description), ("keywords", keywords), ("author", author)]:
        if value.strip():
            lines.append(f'<meta name="{name}" content="{_escape(value.strip())}" />')
    og_title = og_title.strip() or title.strip()
    og_description = og_description.strip() or description.strip()
    for prop, value in [("og:title", og_title), ("og:description", og_description), ("og:image", og_image), ("og:url", og_url)]:
        if value.strip():
            lines.append(f'<meta property="{prop}" content="{_escape(value.strip())}" />')
    if any(line.startswith('<meta property="og:') for line in lines):
        lines.append('<meta property="og:type" content="website" />')
    card = twitter_card.strip() or "summary_large_image"
    for name, value in [("twitter:card", card), ("twitter:title", og_title), ("twitter:description", og_description), ("twitter:image", og_image)]:
        if value.strip():
            lines.append(f'<meta name="{name}" content="{_escape(value.strip())}" />')
    if not lines:
        raise ToolError("No metadata provided.")
    return ok("\n".join(lines), title="Meta Tag Generator")


_register(make_tool("meta-tag-generator", meta_tag_generator, title="Meta Tag Generator", hint="title|description|keywords|author|og_title|og_desc|og_image|og_url|twitter_card"))


# --------------------------------------------------------------------------
# OG / SERP previews
# --------------------------------------------------------------------------

def og_preview(item: Input) -> Output:
    title, site, description, image, url = split_pipe(item.require_text(), 5, from_right=False, strip=False)
    domain = site.strip()
    if not domain and url.strip():
        domain = urllib.parse.urlparse(url.strip()).netloc
    summary = f"{title.strip() or '(no title)'}\n{domain or '(no site)'}\n{description.strip() or '(no description)'}\n{image.strip()}"
    page = f"""<!doctype html><html lang="fa" dir="auto"><head><meta charset="utf-8"><title>OG Preview</title>
<style>body{{font-family:Segoe UI,Tahoma,sans-serif;background:#eef1f4;display:flex;justify-content:center;padding:3rem}}
.card{{width:480px;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.15)}}
.img{{height:251px;background:#dfe4e8;display:flex;align-items:center;justify-content:center;color:#8b98a3}}
.img img{{width:100%;height:100%;object-fit:cover}}
.body{{padding:14px 16px}}.site{{font-size:12px;color:#657786;text-transform:uppercase}}
.title{{font-weight:700;font-size:18px;margin-top:4px;color:#1f2933}}.desc{{color:#52606d;font-size:14px;margin-top:4px}}</style>
</head><body><div class="card"><div class="img">{f'<img src="{_escape(image.strip())}" alt="">' if image.strip() else 'No image'}</div>
<div class="body"><div class="site">{_escape(domain)}</div><div class="title">{_escape(title.strip() or '(no title)')}</div>
<div class="desc">{_escape(description.strip() or '(no description)')}</div></div></div></body></html>"""
    path = temp_path("html", "og-preview")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return Output(text=summary, title="Open Graph Preview", open_path=path, message="Preview opened in your browser")


_register(make_tool("og-preview", og_preview, title="Open Graph Preview", hint="title|site|description|image|url"))


def serp_preview(item: Input) -> Output:
    title, url, description = split_pipe(item.require_text(), 3, from_right=False, strip=False)
    crumb = url.strip()
    try:
        parsed = urllib.parse.urlparse(crumb)
        if parsed.netloc:
            crumb = parsed.netloc + ("" if parsed.path in {"", "/"} else parsed.path.replace("/", " > "))
    except Exception:
        pass
    warnings = []
    if len(title) > 60:
        warnings.append(f"Title is {len(title)} characters (recommended max 60).")
    if len(description) > 160:
        warnings.append(f"Description is {len(description)} characters (recommended max 160).")
    body = "\n".join(
        [
            f"{crumb or 'example.com'}",
            title.strip() or "(no title)",
            description.strip() or "(no description)",
            "",
            f"Title length: {len(title)}/60",
            f"Description length: {len(description)}/160",
        ]
    )
    if warnings:
        body += "\n\nWarnings:\n" + "\n".join(warnings)
    return ok(body, title="SERP Preview")


_register(make_tool("serp-preview", serp_preview, title="SERP Preview", hint="title|url|description"))


# --------------------------------------------------------------------------
# robots.txt / sitemap
# --------------------------------------------------------------------------

def robots_generator(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 5, from_right=False, strip=False)
    agent, disallow, allow, sitemap, crawl_delay = parts
    agent = agent.strip() or "*"
    lines = [f"User-agent: {agent}"]
    for path in [line.strip() for line in disallow.splitlines() if line.strip()]:
        lines.append(f"Disallow: {path}")
    for path in [line.strip() for line in allow.splitlines() if line.strip()]:
        lines.append(f"Allow: {path}")
    if crawl_delay.strip():
        lines.append(f"Crawl-delay: {crawl_delay.strip()}")
    for line in [line.strip() for line in sitemap.splitlines() if line.strip()]:
        lines.append(f"Sitemap: {line}")
    return ok("\n".join(lines), title="robots.txt Generator")


_register(make_tool("robots-generator", robots_generator, title="robots.txt Generator", hint="agent|disallow|allow|sitemap|crawl_delay"))


def sitemap_generator(item: Input) -> Output:
    parts = item.require_text().rsplit("|", 3)
    if len(parts) == 1:
        changefreq, priority, lastmod, payload = "", "", "", parts[0]
    elif len(parts) == 2:
        changefreq, priority, lastmod, payload = parts[0], "", "", parts[1]
    elif len(parts) == 3:
        changefreq, priority, lastmod, payload = parts[0], parts[1], "", parts[2]
    else:
        changefreq, priority, lastmod, payload = parts
    urls = [line.strip() for line in payload.splitlines() if line.strip()]
    if not urls:
        raise ToolError("No URLs found.")
    entries = []
    for url in urls:
        lines = ["  <url>", f"    <loc>{_escape(url)}</loc>"]
        if lastmod.strip():
            lines.append(f"    <lastmod>{_escape(lastmod.strip())}</lastmod>")
        if changefreq.strip():
            lines.append(f"    <changefreq>{_escape(changefreq.strip())}</changefreq>")
        if priority.strip():
            lines.append(f"    <priority>{_escape(priority.strip())}</priority>")
        lines.append("  </url>")
        entries.append("\n".join(lines))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(entries) + "\n</urlset>"
    return ok(xml, title="Sitemap Generator")


_register(make_tool("sitemap-generator", sitemap_generator, title="Sitemap Generator", hint="changefreq|priority|lastmod|URLs"))
