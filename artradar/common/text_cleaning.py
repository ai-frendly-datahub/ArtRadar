"""Text normalization helpers for collected article content."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup


def clean_text(value: str | None) -> str:
    """Return readable plain text from RSS/API/browser text fields."""
    if value is None:
        return ""

    text = html.unescape(str(value))
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ")

    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()
