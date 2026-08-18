"""Torq CLI entry point.

This is the bootstrap stub for slice 0.1. The full Click command tree is
introduced in phase 3 (slices 0.21-0.25).
"""

from __future__ import annotations

import click

from torq.version import __version__


@click.command()
@click.version_option(version=__version__, prog_name="torq")
def main() -> None:
    """Torq — terminal-first BitTorrent client."""
    click.echo(f"torq {__version__} (bootstrap — not yet implemented)")
