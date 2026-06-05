from __future__ import annotations

from typing import Any

from multi_agent_video.config import AppConfig


def init_observability(config: AppConfig) -> bool:
    """Initialize optional Sentry observability when SENTRY_DSN is configured."""
    if not config.sentry_dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        return False

    sentry_sdk.init(
        dsn=config.sentry_dsn,
        environment=config.sentry_environment,
        release=config.app_release,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("app", "multi-agent-video")
    sentry_sdk.set_tag("runtime", "streamlit")
    return True


def capture_exception(exc: BaseException, **context: Any) -> None:
    try:
        import sentry_sdk
    except ImportError:
        return

    with sentry_sdk.push_scope() as scope:
        for key, value in context.items():
            scope.set_context(key, value)
        sentry_sdk.capture_exception(exc)
