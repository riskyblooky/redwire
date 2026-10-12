"""Registry of plugin-supplied scoring engines.

A ``ScoringModel`` whose ``formula`` is ``{"engine": "<name>"}`` is evaluated by
the provider registered under ``<name>``. Built-in engines (``builtin-cvss31``)
are handled directly in :mod:`scoring.engine`; everything else is a provider a
plugin registers from its ``setup()`` — modeled on the event-bus pattern
(``utils/event_bus.py``). See ``docs/pluggable-finding-scoring.md`` §7.

A provider is a callable ``fn(inputs: dict) -> (score: float, vector: str|None)``.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ScoringProviderFn = Callable[[Dict], Tuple[float, Optional[str]]]


class ScoringProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, ScoringProviderFn] = {}
        self._owners: Dict[str, Optional[str]] = {}

    def register(self, engine_name: str, fn: ScoringProviderFn, *, plugin_id: Optional[str] = None) -> None:
        if engine_name in self._providers:
            logger.info("scoring engine '%s' re-registered (owner %s)", engine_name, plugin_id)
        self._providers[engine_name] = fn
        self._owners[engine_name] = plugin_id
        logger.info("registered scoring engine '%s'%s", engine_name,
                    f" (plugin {plugin_id})" if plugin_id else "")

    def unregister(self, engine_name: str) -> None:
        self._providers.pop(engine_name, None)
        self._owners.pop(engine_name, None)

    def get(self, engine_name: str) -> Optional[ScoringProviderFn]:
        return self._providers.get(engine_name)

    def names(self) -> List[str]:
        return list(self._providers)


# Process-global singleton (mirrors event_bus / scoring_registry).
scoring_provider_registry = ScoringProviderRegistry()
