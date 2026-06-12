"""Zendesk scraper — fetches articles from the Help Center API and converts to Markdown."""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from src.types import Article

log = logging.getLogger("scraper")

API_PATH = "/api/v2/help_center/en-us/articles.json"
USER_AGENT = "OptiBot-Mini-Clone/0.1.0"
PAGE_DELAY_S = 0.5  # polite delay between paginated requests


def _slug_from_url(html_url: str) -> str:
    """Extract a filesystem-safe slug from the article's html_url.

    Example: "https://support.optisigns.com/hc/en-us/articles/52523606879251-OptiSigns-Digital-Signage-..."
    → "optisigns-digital-signage-app-for-zoom"
    """
    # Last path segment after the ID
    m = re.search(r"/articles/\d+-(.+)$", html_url)
    if m:
        return m.group(1).rstrip("/")
    # Fallback: use the article ID
    m = re.search(r"/articles/(\d+)", html_url)
    return m.group(1) if m else "unknown"


def _clean_html(html: str) -> str:
    """Strip nav, ads, and extraneous elements from Zendesk article HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove elements that are clearly navigation/sidebar/ads
    for selector in [
        "nav",
        "header",
        "footer",
        ".sidebar",
        "#sidebar",
        ".related-articles",
        ".article-attachments",
        ".article-votes",
        ".article-share",
        ".article-return-to-top",
        ".breadcrumbs",
        ".search-box",
        "[role=navigation]",
        "[aria-label*=navigation i]",
        ".promoted-articles",
        ".recent-articles",
        ".section-subscribe",
        ".article-subscribe",
        ".meta-data",
    ]:
        for tag in soup.select(selector):
            tag.decompose()

    return str(soup)


def _html_to_markdown(html: str) -> str:
    """Convert cleaned Zendesk article HTML to Markdown."""
    cleaned = _clean_html(html)

    options = {
        "heading_style": "ATX",  # ## headings
        "bullets": "-",
        "code_language": "",
        "code_style": "fenced",
        "strip": ["img", "script", "style"],
        "escape_asterisks": False,
        "escape_underscores": False,
        "escape_misc": False,
    }

    markdown = md(cleaned, **options)

    # Collapse excessive blank lines (max 2)
    # Collapse excessive blank lines (max 2)
    lines = markdown.split("\n")
    cleaned: list[str] = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(line.rstrip())
    markdown = "\n".join(cleaned)
    return markdown.strip() + "\n"


def fetch_all_articles(base_url: str) -> list[dict]:
    """Fetch all non-draft articles from Zendesk Help Center (paginated)."""
    articles: list[dict] = []
    url = urljoin(base_url.rstrip("/") + "/", API_PATH.lstrip("/"))
    page = 0

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    while url:
        page += 1
        log.info("Fetching article page %d ...", page)
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("Failed to fetch page %d: %s", page, exc)
            break

        data = resp.json()
        for raw in data.get("articles", []):
            if raw.get("draft", False):
                continue
            articles.append(raw)

        url = data.get("next_page")
        if url:
            time.sleep(PAGE_DELAY_S)

    log.info("Fetched %d non-draft articles across %d pages", len(articles), page)
    return articles


def run_scraper(cfg) -> list[Article]:
    """Fetch articles from Zendesk Help Center and save as Markdown files.

    Returns the list of Article objects (with .md files already on disk).
    """
    os.makedirs(cfg.data_dir, exist_ok=True)

    raw_articles = fetch_all_articles(cfg.zendesk_base_url)
    parsed: list[Article] = []

    for raw in raw_articles:
        slug = _slug_from_url(raw["html_url"])
        body_md = _html_to_markdown(raw["body"])

        article = Article(
            id=raw["id"],
            title=raw["title"],
            slug=slug,
            body_html=raw["body"],
            md_content=body_md,
            updated_at=raw["updated_at"],
            html_url=raw["html_url"],
        )

        # Write Markdown file with YAML frontmatter
        frontmatter = (
            "---\n"
            f'title: "{article.title}"\n'
            f"url: {article.html_url}\n"
            f"updated_at: {article.updated_at}\n"
            "---\n\n"
        )
        filepath = os.path.join(cfg.data_dir, f"{slug}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter + body_md)

        parsed.append(article)
        log.debug("Saved %s (%d chars)", filepath, len(body_md))

    log.info("Scraped %d articles → %s/", len(parsed), cfg.data_dir)
    return parsed
