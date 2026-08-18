"""Torq daemon entry point.

Bootstrap stub for slice 0.1. Lifecycle and local API land in slices 0.15-0.20.
"""

from __future__ import annotations

import click

from torq.version import __version__


@click.command()
@click.version_option(version=__version__, prog_name="torqd")
def main() -> None:
    """Torq daemon — placeholder for slice 0.15+."""
    click.echo(f"torqd {__version__} (bootstrap — not yet implemented)")
