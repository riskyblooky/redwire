"""Registry of available scoring models.

Built-in models are JSON files in ``scoring/models/``. Plugins register
additional models at load time via :meth:`ScoringRegistry.register` (see
``docs/pluggable-finding-scoring.md`` §7). The registry is a process-global
singleton, mirroring the plugin registry pattern.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

from scoring.types import ScoringModel

logger = logging.getLogger(__name__)

_MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

# The model used when a finding has no explicit score_model (legacy findings).
DEFAULT_MODEL_ID = "cvss31"


class ScoringRegistry:
    def __init__(self) -> None:
        self._models: Dict[str, ScoringModel] = {}
        self._loaded_builtins = False

    # ── loading ──────────────────────────────────────────────────────────────
    def load_builtins(self, force: bool = False) -> None:
        if self._loaded_builtins and not force:
            return
        if not os.path.isdir(_MODELS_DIR):
            logger.warning("scoring models dir missing: %s", _MODELS_DIR)
            self._loaded_builtins = True
            return
        for name in sorted(os.listdir(_MODELS_DIR)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(_MODELS_DIR, name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                model = ScoringModel.model_validate(data)
                model.source = "builtin"
                self._models[model.id] = model
            except Exception as exc:  # noqa: BLE001 - one bad file must not break boot
                logger.error("failed to load scoring model %s: %s", path, exc)
        self._loaded_builtins = True
        logger.info("loaded %d built-in scoring models", len(self._models))

    def register(self, model: ScoringModel, *, source: Optional[str] = None) -> None:
        """Register a model (e.g. plugin-contributed). Later registrations with
        the same id override earlier ones."""
        if source:
            model.source = source
        if model.id in self._models and self._models[model.id].source != model.source:
            logger.info("scoring model '%s' overridden by %s", model.id, model.source)
        self._models[model.id] = model

    def unregister(self, model_id: str) -> None:
        self._models.pop(model_id, None)

    # ── access ───────────────────────────────────────────────────────────────
    def get(self, model_id: str) -> Optional[ScoringModel]:
        self.load_builtins()
        return self._models.get(model_id)

    def require(self, model_id: str) -> ScoringModel:
        model = self.get(model_id)
        if model is None:
            raise KeyError(f"unknown scoring model '{model_id}'")
        return model

    def list(self) -> List[ScoringModel]:
        self.load_builtins()
        return list(self._models.values())

    def ids(self) -> List[str]:
        self.load_builtins()
        return list(self._models.keys())


# Process-global singleton.
scoring_registry = ScoringRegistry()
