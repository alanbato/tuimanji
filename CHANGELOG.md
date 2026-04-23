# Changelog

All notable changes to tuimanji will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-04-17

Initial public release.

### Added

- Pubnix-local multiplayer over a shared SQLite WAL database at
  `$TUIMANJI_DB/tuimanji.db`.
- Textual-based TUI with a lobby, waiting room, and in-match canvas.
- Nine games:
  - Tic-Tac-Toe (2p)
  - Connect 4 (2p) — with falling-piece animation
  - Battleship (2p) — place phase + fire phase, hidden opponent grid
  - Reversi / Othello (2p) — with flip-cascade animation
  - Chess (2p) — full FIDE rules minus draw-by-repetition / 50-move /
    insufficient-material
  - Checkers / English draughts (2p) — forced captures, multi-jump chains
  - Peg Solitaire (1p) — English cross board
  - Crazy Eights (2-4p) — wild eights with suit choice, hidden hands
  - Royal Game of Ur (2p) — Finkel rules, dice roll phase, rosettes
- Session slot identity via `flock`, letting two terminals for the same
  unix user claim distinct player ids (`user`, `user#2`, …).
- Typer CLI with `new`, `join`, `resume`, `games`, `where`, `--version`.
- `TUIMANJI_DB` environment variable (and `--db` flag) to override the
  shared database directory.
- Crash-resume — relaunching into an in-flight match preserves seat and
  turn state from the append-only logs.
- Public Python API: `tuimanji.Game`, exceptions, and the game registry
  are importable for third-party game authors.

[Unreleased]: https://github.com/alanbato/tuimanji/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/alanbato/tuimanji/releases/tag/v0.1.0
