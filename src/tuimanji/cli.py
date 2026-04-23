"""Typer CLI for tuimanji.

The default invocation (``tuimanji``) drops into the lobby. Subcommands are
shortcuts around the same launch modes the lobby exposes interactively:

- ``tuimanji new <game>``  — create a new match and jump into its waiting room
- ``tuimanji join <id>``   — join (or rejoin) an existing match by id
- ``tuimanji resume``      — open the most recent unfinished match
- ``tuimanji games``       — list available games with their player counts
- ``tuimanji where``       — print the resolved database directory

Backward-compatible flag form on the default command (``--new``, ``--join``,
``--resume``) is preserved so existing muscle memory and scripts keep working.

All subcommands honor ``--db PATH`` / ``TUIMANJI_DB`` to override the shared
SQLite directory (default: ``/var/games/tuimanji``).
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from . import __version__
from .games import REGISTRY

app = typer.Typer(
    name="tuimanji",
    help="Pubnix-local turn-based multiplayer TUI.",
    no_args_is_help=False,
    add_completion=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"tuimanji {__version__}")
        raise typer.Exit()


def _apply_db(db: Path | None) -> None:
    if db is not None:
        os.environ["TUIMANJI_DB"] = str(db)


def _launch(
    resume: bool = False,
    new_game_id: str | None = None,
    join_match_id: str | None = None,
) -> None:
    # Deferred so --help and --version don't pay Textual's import cost.
    from .app import TuimanjiApp

    TuimanjiApp(
        resume=resume,
        new_game_id=new_game_id,
        join_match_id=join_match_id,
    ).run()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    resume: bool = typer.Option(
        False,
        "--resume",
        "-r",
        help="Jump straight into your most recent unfinished match.",
    ),
    new: str | None = typer.Option(
        None,
        "--new",
        "-n",
        metavar="GAME",
        help="Create a new match for GAME and jump into its waiting room.",
    ),
    join: str | None = typer.Option(
        None,
        "--join",
        "-j",
        metavar="MATCH_ID",
        help="Join (or rejoin) an existing match by id.",
    ),
    db: Path | None = typer.Option(
        None,
        "--db",
        envvar="TUIMANJI_DB",
        help="Directory holding the shared SQLite database. Defaults to "
        "/var/games/tuimanji.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """Tuimanji — pubnix-local turn-based multiplayer."""
    _apply_db(db)
    if ctx.invoked_subcommand is not None:
        return
    if sum([resume, new is not None, join is not None]) > 1:
        raise typer.BadParameter("--resume, --new, and --join are mutually exclusive")
    if new is not None and new not in REGISTRY:
        valid = ", ".join(sorted(REGISTRY))
        raise typer.BadParameter(
            f"unknown game '{new}'. Valid: {valid}", param_hint="--new"
        )
    _launch(resume=resume, new_game_id=new, join_match_id=join)


@app.command("new")
def cmd_new(
    game: str = typer.Argument(
        ...,
        metavar="GAME",
        help="Game id (see `tuimanji games`).",
    ),
) -> None:
    """Create a new match for GAME and jump into its waiting room."""
    if game not in REGISTRY:
        valid = ", ".join(sorted(REGISTRY))
        raise typer.BadParameter(
            f"unknown game '{game}'. Valid: {valid}", param_hint="GAME"
        )
    _launch(new_game_id=game)


@app.command("join")
def cmd_join(
    match_id: str = typer.Argument(..., metavar="MATCH_ID", help="Match id to join."),
) -> None:
    """Join (or rejoin) an existing match by id."""
    _launch(join_match_id=match_id)


@app.command("resume")
def cmd_resume() -> None:
    """Jump straight into your most recent unfinished match."""
    _launch(resume=True)


@app.command("games")
def cmd_games() -> None:
    """List available games with player counts."""
    width = max(len(g.id) for g in REGISTRY.values())
    for g in REGISTRY.values():
        if g.min_players == g.max_players:
            players = f"{g.min_players}p"
        else:
            players = f"{g.min_players}-{g.max_players}p"
        typer.echo(f"  {g.id:<{width}}  {players:<5}  {g.name}")


@app.command("where")
def cmd_where() -> None:
    """Print the resolved database directory."""
    from .db import db_dir

    typer.echo(str(db_dir()))


def main() -> None:
    """Console-script entry point."""
    app()
