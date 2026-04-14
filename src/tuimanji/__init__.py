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
) -> None:
    """Tuimanji — pubnix-local turn-based multiplayer."""
    if resume and new is not None:
        raise typer.BadParameter("--resume and --new are mutually exclusive")
    if new is not None and new not in REGISTRY:
        valid = ", ".join(sorted(REGISTRY))
        raise typer.BadParameter(
            f"unknown game '{new}'. Valid: {valid}", param_hint="--new"
        )
    TuimanjiApp(resume=resume, new_game_id=new).run()


def main() -> None:
    typer.run(_run)
