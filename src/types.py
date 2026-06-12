"""Shared type aliases and data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Article:
    """A single Zendesk Help Center article."""

    id: int
    title: str
    slug: str
    body_html: str
    md_content: str
    updated_at: str
    html_url: str


@dataclass
class ArticleState:
    """Persisted state for a single article — used for delta detection."""

    slug: str
    sha256: str
    last_modified: str


@dataclass
class DeltaResult:
    """Result of comparing current articles against persisted state."""

    added: list[Article] = field(default_factory=list)
    updated: list[Article] = field(default_factory=list)
    skipped: list[Article] = field(default_factory=list)
