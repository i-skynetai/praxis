"""Adapters. Provider names live here and nowhere else.

``fake`` and the chat-completions adapter ship with the core and need nothing beyond the
standard library. Every other adapter is a pip extra and imports its dependency lazily
through ``praxis_core.providers._extras.require``, so ``import praxis_core.providers``
never pulls a vendor SDK and a missing extra fails with the line that installs it.

The CLI and the demo reach adapters through the neutral factories below, so no vendor
name appears outside this package (a test enforces it).
"""

from __future__ import annotations

from typing import Any


def chat_completions_adapter(base_url: str, model: str, api_key: str | None = None, **options: Any) -> Any:
    """The adapter for any server speaking the chat-completions wire protocol: a local
    model server, a proxy, or the hosted API. Serves as teacher, System-1 or generative
    student; see the module it comes from."""
    from .openai_compat import OpenAICompatible

    return OpenAICompatible(base_url, model, api_key, **options)
