import unittest

from app.services.news_parser import get_new_content


class FakeResponse:
    def __init__(self, html: str, error: Exception | None = None):
        self.html = html
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self):
        if self.error:
            raise self.error

    async def text(self):
        return self.html


class FakeSession:
    def __init__(self, html: str, error: Exception | None = None):
        self.html = html
        self.error = error

    def get(self, url: str, headers: dict):
        return FakeResponse(self.html, self.error)


class NewsParserTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_empty_text_for_unknown_layout(self):
        content = await get_new_content(
            "https://example.test/news", FakeSession("<html></html>")
        )
        self.assertEqual(content, "")

    async def test_extracts_article_and_removes_trash(self):
        html = (
            '<div class="article__text">'
            '<div class="banner-advert">Реклама</div>'
            "<p>Первый абзац</p><p>Второй абзац</p>"
            "</div>"
        )
        content = await get_new_content(
            "https://example.test/news", FakeSession(html)
        )
        self.assertEqual(content, "Первый абзац\n\nВторой абзац")

    async def test_returns_empty_text_on_http_error(self):
        content = await get_new_content(
            "https://example.test/news",
            FakeSession("", RuntimeError("upstream unavailable")),
        )
        self.assertEqual(content, "")
