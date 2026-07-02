#!/usr/bin/env python3
"""
Alembic migration runner with plugin-branch discovery.

Standard Alembic doesn't know about plugin migration directories because
``version_locations`` is read by ``ScriptDirectory`` before ``env.py``
gets a chance to run. This wrapper discovers plugin migration dirs and
sets ``version_locations`` on the Alembic Config programmatically, then
invokes the requested command.

Each plugin can ship migrations at::

    plugins/<slug>/alembic/versions/*.py

The first migration in a plugin's chain should declare a branch label so
its history stays disjoint from core::

    revision = "abc123..."
    down_revision = None
    branch_labels = ("plugin:my-plugin",)

Subsequent migrations in the same plugin reference their own predecessors.

Usage (drop-in replacement for the ``alembic`` CLI):

    python migrate.py upgrade heads
    python migrate.py downgrade -1
    python migrate.py revision --autogenerate -m "add x"
    python migrate.py revision --autogenerate --branch-label=plugin:foo -m "..."
    python migrate.py current
    python migrate.py history

Use ``upgrade heads`` (plural) — with plugin branches present, there's
more than one head to advance. ``upgrade head`` (singular) errors out
when multiple heads exist; that's Alembic's intended behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config, CommandLine

_HERE = Path(__file__).resolve().parent


def _discover_plugin_version_dirs() -> list[str]:
    """Return every plugins/<slug>/alembic/versions/ dir that exists."""
    plugins_root = _HERE / "plugins"
    if not plugins_root.is_dir():
        return []
    dirs: list[str] = []
    for entry in sorted(plugins_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        vdir = entry / "alembic" / "versions"
        if vdir.is_dir():
            dirs.append(str(vdir))
    return dirs


def _make_config(argv: list[str]) -> Config:
    """Build the Alembic Config with plugin version dirs merged in.

    Uses Alembic's own CommandLine to parse argv so all built-in flags
    (``-c``, ``-x``, verbose, etc.) still work, then hijacks the Config
    before the command runs. See CommandLine.main() for the ordering.
    """
    cli = CommandLine(prog="migrate.py")
    options = cli.parser.parse_args(argv)
    if not hasattr(options, "cmd"):
        cli.parser.error("no command specified")
    cfg = Config(
        file_=options.config,
        ini_section=options.name,
        cmd_opts=options,
    )
    # Merge core versions dir with discovered plugin dirs. Core comes
    # first so an autogenerate without --branch-label defaults there.
    core_dir = str(_HERE / "alembic" / "versions")
    plugin_dirs = _discover_plugin_version_dirs()
    if plugin_dirs:
        cfg.set_main_option(
            "version_locations",
            " ".join([core_dir] + plugin_dirs),
        )
        print(
            f"[migrate] discovered {len(plugin_dirs)} plugin migration "
            f"director{'y' if len(plugin_dirs) == 1 else 'ies'}: "
            + ", ".join(Path(d).parent.parent.name for d in plugin_dirs),
            file=sys.stderr,
        )
    return cfg, cli, options


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    cfg, cli, options = _make_config(argv)
    # CommandLine.run_cmd invokes the parsed command against the config.
    cli.run_cmd(cfg, options)
    return 0


if __name__ == "__main__":
    sys.exit(main())
