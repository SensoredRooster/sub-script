"""Multi-platform publish package.

``publish_local`` builds the shared social pack under ``out/approved/<id>/``.
Enabled platform publishers fan out on Approve (YouTube live API when configured;
other platforms default to ``for_<platform>/`` + ``POST_INSTRUCTIONS.txt``).
"""

from __future__ import annotations

from subscript.publish.base import NotConfiguredError, PublishMeta, PublishResult, Publisher
from subscript.publish.local import publish_local
from subscript.publish.orchestrator import (
    build_publishers,
    format_platform_banner,
    run_enabled_publishers,
)

__all__ = [
    "NotConfiguredError",
    "PublishMeta",
    "PublishResult",
    "Publisher",
    "build_publishers",
    "format_platform_banner",
    "publish_local",
    "run_enabled_publishers",
]
