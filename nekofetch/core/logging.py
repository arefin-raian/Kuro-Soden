"""Structured logging via structlog.

Console-friendly key=value rendering by default; JSON when ``LOG_JSON=true`` for
production log aggregation. Call :func:`configure_logging` once at startup.
"""

from __future__ import annotations

import logging
import sys

import structlog


class _SuppressPyrogramNoise(logging.Filter):
    """Drop Pyrogram retry noise that we can't control.

    ``PERSISTENT_TIMESTAMP_OUTDATED`` is a Telegram-server-side hiccup that
    Pyrogram retries automatically — the repeated log lines are just noise.
    """
    _NOISE = (
        "PERSISTENT_TIMESTAMP_OUTDATED",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(pat in msg for pat in self._NOISE)


def configure_logging(level: str = "INFO", json: bool = False, rich: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    # Suppress Pyrogram's endless retry noise for Telegram server hiccups.
    for name in ("pyrogram", "pyrogram.dispatcher", "pyrogram.client",
                 "pyrogram.session", "pyrogram.session.session",
                 "pyrogram.session.auth", "pyrogram.connection"):
        logging.getLogger(name).addFilter(_SuppressPyrogramNoise())

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json:
        processors.append(structlog.processors.JSONRenderer())
    elif rich:
        from nekofetch.ui.terminal import rich_processor
        processors.append(rich_processor)
    else:
        colors = True
        if sys.platform == "win32":
            try:
                import colorama
                colorama.init()
            except ImportError:
                colors = False
        processors.append(structlog.dev.ConsoleRenderer(colors=colors))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
