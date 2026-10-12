"""CVSS 4.0 scoring plugin.

Contributes CVSS 4.0 (CVSS-B) as a finding scoring model through the pluggable
scoring contract:
  - a DECLARATIVE model (``models/cvss40.json``) loaded by the plugin loader
    from ``provides.scoring_models``; and
  - a Python ENGINE (``cvss4_engine``, a faithful port of FIRST.org's reference
    implementation) registered here as a scoring provider for the model's
    ``formula.engine: "cvss40"``.

The generic scoring calculator renders the model's metrics and evaluates them
through this provider server-side — so CVSS 4.0 needs no custom frontend code.
"""

from scoring.providers import scoring_provider_registry

from .cvss4_engine import calculate as _cvss4_calculate


def _cvss40_provider(inputs):
    """inputs: the 11 CVSS 4.0 base metrics. Returns (score, vector_string)."""
    return _cvss4_calculate(inputs)


def setup(app, event_bus, db_factory, manifest):
    scoring_provider_registry.register("cvss40", _cvss40_provider, plugin_id=manifest.id)
