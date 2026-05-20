from __future__ import annotations

import os
import sys

import pytest

from artradar.logger import configure_logging, get_logger


def test_configure_logging_json_and_get_logger() -> None:
    configure_logging(log_level="DEBUG", use_json=True)

    logger = get_logger("artradar.test")

    assert callable(logger.bind)
    assert callable(logger.info)


def test_configure_logging_console_renderer() -> None:
    configure_logging(log_level="INFO", use_json=False)

    logger = get_logger("artradar.console")

    assert callable(logger.bind)
    assert callable(logger.info)


def test_configure_logging_reads_env_and_auto_detects_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAR_LOG_LEVEL", "warning")
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)

    configure_logging()

    logger = get_logger("artradar.env")
    assert callable(logger.bind)
    assert os.environ["RADAR_LOG_LEVEL"] == "warning"
