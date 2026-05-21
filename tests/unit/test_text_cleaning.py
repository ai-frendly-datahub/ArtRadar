from __future__ import annotations

import pytest

from artradar.common.text_cleaning import clean_text


@pytest.mark.unit
def test_clean_text_strips_html_and_collapses_whitespace() -> None:
    assert clean_text("<p>Art&nbsp;<b>market</b></p>\n<p>opens</p>") == "Art market opens"


@pytest.mark.unit
def test_clean_text_removes_script_content() -> None:
    assert clean_text("<script>alert(1)</script><p>Visible</p>") == "Visible"


@pytest.mark.unit
def test_clean_text_handles_none() -> None:
    assert clean_text(None) == ""
