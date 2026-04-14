import typer

from .app import TuimanjiApp
from .games import REGISTRY


def _run(
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
) -> None:
    """Tuimanji — pubnix-local turn-based multiplayer."""
    if sum([resume, new is not None, join is not None]) > 1:
        raise typer.BadParameter("--resume, --new, and --join are mutually exclusive")
    if new is not None and new not in REGISTRY:
        valid = ", ".join(sorted(REGISTRY))
        raise typer.BadParameter(
            f"unknown game '{new}'. Valid: {valid}", param_hint="--new"
        )
    TuimanjiApp(resume=resume, new_game_id=new, join_match_id=join).run()


def main() -> None:
    typer.run(_run)
