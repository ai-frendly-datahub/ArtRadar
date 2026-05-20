from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from artradar.notifier import (
    CompositeNotifier,
    EmailNotifier,
    NotificationPayload,
    WebhookNotifier,
)


def _payload() -> NotificationPayload:
    return NotificationPayload(
        category_name="art",
        sources_count=3,
        collected_count=12,
        matched_count=8,
        errors_count=1,
        timestamp=datetime(2026, 5, 21, 1, 2, 3, tzinfo=UTC),
        report_url="reports/art_report.html",
    )


def test_notification_payload_to_dict_uses_iso_timestamp() -> None:
    data = _payload().to_dict()

    assert data["category_name"] == "art"
    assert data["timestamp"] == "2026-05-21T01:02:03+00:00"
    assert data["report_url"] == "reports/art_report.html"


def test_email_notifier_sends_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int) -> None:
            sent["host"] = host
            sent["port"] = port

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def starttls(self) -> None:
            sent["tls"] = True

        def login(self, user: str, password: str) -> None:
            sent["login"] = (user, password)

        def send_message(self, message: object) -> None:
            sent["message"] = message

    monkeypatch.setattr("artradar.notifier.smtplib.SMTP", FakeSMTP)

    notifier = EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user",
        smtp_password="pass",
        from_addr="from@example.com",
        to_addrs=["to@example.com"],
    )

    assert notifier.send(_payload()) is True
    assert sent["host"] == "smtp.example.com"
    assert sent["port"] == 587
    assert sent["login"] == ("user", "pass")
    assert sent["tls"] is True


def test_email_notifier_returns_false_on_smtp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenSMTP:
        def __init__(self, host: str, port: int) -> None:
            raise OSError("smtp down")

    monkeypatch.setattr("artradar.notifier.smtplib.SMTP", BrokenSMTP)
    notifier = EmailNotifier("smtp.example.com", 587, "user", "pass", "from", ["to"])

    assert notifier.send(_payload()) is False


def test_webhook_notifier_post_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_post(
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: int,
    ) -> SimpleNamespace:
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return SimpleNamespace(status_code=204)

    monkeypatch.setattr("artradar.notifier.requests.post", fake_post)

    notifier = WebhookNotifier("https://hooks.example.com/radar", headers={"X-Test": "1"})

    assert notifier.send(_payload()) is True
    assert calls[0]["url"] == "https://hooks.example.com/radar"
    assert calls[0]["headers"] == {"X-Test": "1"}


def test_webhook_notifier_handles_get_status_and_invalid_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artradar.notifier.requests.get",
        lambda url, *, headers, timeout: SimpleNamespace(status_code=500),
    )

    assert (
        WebhookNotifier("https://hooks.example.com/radar", method="GET").send(_payload()) is False
    )
    assert (
        WebhookNotifier("https://hooks.example.com/radar", method="PATCH").send(_payload()) is False
    )


def test_webhook_notifier_returns_false_on_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_post(*args: object, **kwargs: object) -> object:
        raise RuntimeError("network")

    monkeypatch.setattr("artradar.notifier.requests.post", failing_post)

    assert WebhookNotifier("https://hooks.example.com/radar").send(_payload()) is False


def test_composite_notifier_aggregates_results() -> None:
    success = SimpleNamespace(send=lambda payload: True)
    failure = SimpleNamespace(send=lambda payload: False)
    raises = SimpleNamespace(send=lambda payload: (_ for _ in ()).throw(RuntimeError("boom")))

    assert CompositeNotifier([]).send(_payload()) is True
    assert CompositeNotifier([success]).send(_payload()) is True
    assert CompositeNotifier([success, failure]).send(_payload()) is False
    assert CompositeNotifier([success, raises]).send(_payload()) is False
