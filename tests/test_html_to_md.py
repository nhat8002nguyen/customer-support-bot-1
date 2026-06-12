"""Tests for HTML-to-Markdown conversion in the scraper."""

from src.scraper import _clean_html, _html_to_markdown


class TestCleanHtml:
    def test_strips_nav_tags(self):
        html = "<nav>Navigation</nav><div>Content</div>"
        result = _clean_html(html)
        assert "Navigation" not in result
        assert "Content" in result

    def test_strips_footer(self):
        html = "<footer>Footer</footer><p>Body</p>"
        result = _clean_html(html)
        assert "Footer" not in result
        assert "Body" in result

    def test_preserves_article_body(self):
        html = "<article><h1>Title</h1><p>Content</p></article>"
        result = _clean_html(html)
        assert "Title" in result
        assert "Content" in result


class TestHtmlToMarkdown:
    def test_converts_heading(self):
        html = "<h1>Hello World</h1>"
        result = _html_to_markdown(html)
        assert "# Hello World" in result

    def test_converts_code_block(self):
        html = "<pre><code>print('hello')</code></pre>"
        result = _html_to_markdown(html)
        assert "print('hello')" in result

    def test_converts_unordered_list(self):
        html = "<ul><li>One</li><li>Two</li></ul>"
        result = _html_to_markdown(html)
        assert "- One" in result
        assert "- Two" in result

    def test_preserves_relative_links(self):
        html = '<a href="/hc/en-us/articles/123">Link</a>'
        result = _html_to_markdown(html)
        assert "/hc/en-us/articles/123" in result

    def test_collapses_excessive_blank_lines(self):
        html = "<p>A</p><br/><br/><br/><br/><p>B</p>"
        result = _html_to_markdown(html)
        lines = result.split("\n")
        blank_runs = 0
        current_run = 0
        for line in lines:
            if line.strip() == "":
                current_run += 1
            else:
                blank_runs = max(blank_runs, current_run)
                current_run = 0
        assert blank_runs <= 2, f"Too many consecutive blank lines: {blank_runs}"
