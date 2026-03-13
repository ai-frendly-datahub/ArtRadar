from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests

from artradar.models import Source

@pytest.mark.unit
def test_collect_met_museum_parses_response() -> None:
    from artradar.collector import _collect_met_museum

    source = Source(
        name="Metropolitan Museum",
        type="met_museum",
        url="https://collectionapi.metmuseum.org/public/collection/v1/objects",
    )
    search_response = SimpleNamespace(
        json=lambda: {"objectIDs": [1]}, raise_for_status=lambda: None
    )
    object_response = SimpleNamespace(
        json=lambda: {
            "title": "Sunflowers",
            "artistDisplayName": "Vincent van Gogh",
            "objectDate": "1887",
            "medium": "Oil on canvas",
            "objectURL": "https://www.metmuseum.org/art/collection/search/1",
            "metadataDate": "2018-10-17T10:24:43.197Z",
        },
        raise_for_status=lambda: None,
    )

    with patch(
        "artradar.collector._fetch_url_with_retry", side_effect=[search_response, object_response]
    ):
        articles = _collect_met_museum(source, category="art", limit=1, timeout=15)

    assert len(articles) == 1
    assert articles[0].title == "Sunflowers"
    assert "Vincent van Gogh" in articles[0].summary


@pytest.mark.unit
def test_collect_aic_parses_response() -> None:
    from artradar.collector import _collect_aic

    source = Source(
        name="Art Institute of Chicago", type="aic", url="https://api.artic.edu/api/v1/artworks"
    )
    response = SimpleNamespace(
        json=lambda: {
            "data": [
                {
                    "id": 4,
                    "title": "Priest and Boy",
                    "artist_display": "Lawrence Carmichael Earle",
                    "date_display": "n.d.",
                    "medium_display": "Watercolor",
                    "department_title": "Prints and Drawings",
                }
            ]
        },
        raise_for_status=lambda: None,
    )

    with patch("artradar.collector._fetch_url_with_retry", return_value=response):
        articles = _collect_aic(source, category="art", limit=1, timeout=15)

    assert len(articles) == 1
    assert articles[0].link == "https://www.artic.edu/artworks/4"
    assert "Lawrence Carmichael Earle" in articles[0].summary


@pytest.mark.unit
def test_collect_smithsonian_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from artradar.collector import _collect_smithsonian
    from artradar.exceptions import SourceError

    monkeypatch.delenv("SMITHSONIAN_API_KEY", raising=False)
    source = Source(
        name="Smithsonian", type="smithsonian", url="https://api.si.edu/openaccess/api/v1.0/search"
    )

    with pytest.raises(SourceError):
        _ = _collect_smithsonian(source, category="art", limit=1, timeout=15)


@pytest.mark.unit
def test_collect_smithsonian_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    from artradar.collector import _collect_smithsonian

    monkeypatch.setenv("SMITHSONIAN_API_KEY", "test-key")
    source = Source(
        name="Smithsonian", type="smithsonian", url="https://api.si.edu/openaccess/api/v1.0/search"
    )
    response = SimpleNamespace(
        json=lambda: {
            "response": {
                "rows": [
                    {
                        "id": "edanmdm-test",
                        "title": "Smithsonian Object",
                        "timestamp": "1592467904",
                        "content": {
                            "descriptiveNonRepeating": {
                                "record_link": "https://collections.si.edu/search/detail",
                                "data_source": "National Museum of Asian Art",
                            },
                            "freetext": {
                                "notes": [{"label": "Summary", "content": "A museum object."}]
                            },
                        },
                    }
                ]
            }
        },
        raise_for_status=lambda: None,
    )

    with patch("artradar.collector._fetch_url_with_retry", return_value=response):
        articles = _collect_smithsonian(source, category="art", limit=1, timeout=15)

    assert len(articles) == 1
    assert articles[0].title == "Smithsonian Object"
    assert articles[0].source == "National Museum of Asian Art"


@pytest.mark.unit
def test_api_timeout_raises_network_error() -> None:
    from artradar.collector import _collect_aic
    from artradar.exceptions import NetworkError

    source = Source(
        name="Art Institute of Chicago", type="aic", url="https://api.artic.edu/api/v1/artworks"
    )

    with patch(
        "artradar.collector._fetch_url_with_retry",
        side_effect=requests.exceptions.Timeout("timeout"),
    ):
        with pytest.raises(NetworkError):
            _ = _collect_aic(source, category="art", limit=1, timeout=15)


@pytest.mark.unit
def test_malformed_json_raises_parse_error() -> None:
    from artradar.collector import _collect_met_museum
    from artradar.exceptions import ParseError

    source = Source(
        name="Metropolitan Museum",
        type="met_museum",
        url="https://collectionapi.metmuseum.org/public/collection/v1/objects",
    )
    bad_response = SimpleNamespace(
        json=lambda: (_ for _ in ()).throw(ValueError("bad json")), raise_for_status=lambda: None
    )

    with patch("artradar.collector._fetch_url_with_retry", return_value=bad_response):
        with pytest.raises(ParseError):
            _ = _collect_met_museum(source, category="art", limit=1, timeout=15)


@pytest.mark.unit
def test_collect_sources_dispatches_api_types(monkeypatch: pytest.MonkeyPatch) -> None:
    from artradar.collector import collect_sources

    monkeypatch.setenv("SMITHSONIAN_API_KEY", "test-key")
    sources = [
        Source(name="Metropolitan Museum", type="met_museum", url="https://met.example/api"),
        Source(name="Art Institute of Chicago", type="aic", url="https://aic.example/api"),
        Source(name="Smithsonian", type="smithsonian", url="https://si.example/api"),
    ]

    with (
        patch("artradar.collector._collect_met_museum", return_value=[]),
        patch("artradar.collector._collect_aic", return_value=[]),
        patch("artradar.collector._collect_smithsonian", return_value=[]),
    ):
        articles, errors = collect_sources(sources, category="art")

    assert articles == []
    assert errors == []
