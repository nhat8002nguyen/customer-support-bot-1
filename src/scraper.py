"""Zendesk scraper — fetches articles from the Help Center API and converts to Markdown."""

from __future__ import annotations

import json
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


class ScrapeIncompleteError(Exception):
    """Raised when the Zendesk API cannot be fully fetched after retries."""


def _slug_from_url(html_url: str) -> str:
    """Extract a filesystem-safe slug from the article's html_url.

    Example: "https://support.optisigns.com/hc/en-us/articles/52523606879251-OptiSigns-Digital-Signage-..."
    → "optisigns-digital-signage-app-for-zoom"
    """
    m = re.search(r"/articles/\d+-(.+)$", html_url)
    if m:
        return m.group(1).rstrip("/")
    m = re.search(r"/articles/(\d+)", html_url)
    return m.group(1) if m else "unknown"


def _clean_html(html: str) -> str:
    """Strip nav, ads, and extraneous elements from Zendesk article HTML."""
    soup = BeautifulSoup(html, "html.parser")

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
        "heading_style": "ATX",
        "bullets": "-",
        "code_language": "",
        "code_style": "fenced",
        "strip": ["img", "script", "style"],
        "escape_asterisks": False,
        "escape_underscores": False,
        "escape_misc": False,
    }

    markdown = md(cleaned, **options)

    lines = markdown.split("\n")
    collapsed: list[str] = []
    blank_count = 0
    for line in lines:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                collapsed.append("")
        else:
            blank_count = 0
            collapsed.append(line.rstrip())
    markdown = "\n".join(collapsed)
    return markdown.strip() + "\n"


def _build_frontmatter(article: Article) -> str:
    """Build YAML frontmatter with safely escaped values."""
    return (
        "---\n"
        f"title: {json.dumps(article.title)}\n"
        f"url: {json.dumps(article.html_url)}\n"
        f"updated_at: {json.dumps(article.updated_at)}\n"
        "---\n\n"
    )


def _fetch_page(session: requests.Session, url: str, retries: int) -> requests.Response:
    last_error: requests.RequestException | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries:
                delay = 2 ** (attempt - 1)
                log.warning(
                    "Fetch attempt %d/%d failed (%s); retrying in %ds",
                    attempt,
                    retries,
                    exc,
                    delay,
                )
                time.sleep(delay)

    assert last_error is not None
    raise last_error


def fetch_all_articles(
    base_url: str, max_pages: int = 0, retries: int = 3
) -> list[dict]:
    """Fetch all non-draft articles from Zendesk Help Center (paginated)."""
    articles: list[dict] = []
    url: str | None = urljoin(base_url.rstrip("/") + "/", API_PATH.lstrip("/"))
    pages_fetched = 0

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    while url:
        if max_pages > 0 and pages_fetched >= max_pages:
            break

        page_number = pages_fetched + 1
        log.info("Fetching article page %d ...", page_number)
        try:
            response = _fetch_page(session, url, retries)
        except requests.RequestException as exc:
            log.error("Failed to fetch page %d after %d retries: %s", page_number, retries, exc)
            raise ScrapeIncompleteError(
                f"Failed to fetch Zendesk page {page_number}: {exc}"
            ) from exc

        pages_fetched += 1
        data = response.json()
        for raw in data.get("articles", []):
            if raw.get("draft", False):
                continue
            articles.append(raw)

        url = data.get("next_page")
        if url:
            time.sleep(PAGE_DELAY_S)

    log.info(
        "Fetched %d non-draft articles across %d pages",
        len(articles),
        pages_fetched,
    )
    return articles


def run_scraper(cfg) -> list[Article]:
    """Fetch articles from Zendesk Help Center and save as Markdown files.

    Returns the list of Article objects (with .md files already on disk).
    """
    os.makedirs(cfg.data_dir, exist_ok=True)

    raw_articles = fetch_all_articles(
        cfg.zendesk_base_url,
        max_pages=cfg.max_pages,
        retries=cfg.fetch_retries,
    )
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

        frontmatter = _build_frontmatter(article)
        file_content = frontmatter + body_md
        article.md_content = file_content

        filepath = os.path.join(cfg.data_dir, f"{slug}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(file_content)

        parsed.append(article)
        log.debug("Saved %s (%d chars)", filepath, len(file_content))

    log.info("Scraped %d articles → %s/", len(parsed), cfg.data_dir)
    return parsed
