<!--
Thanks for contributing! Please fill in the sections below. Small PRs with
clear scope are easiest to review.
-->

## Summary

<!-- One paragraph on what this PR does and why. -->

## Changes

- <!-- bullet list of notable changes -->

## Design notes

<!--
Anything non-obvious. Especially call out:
- New assumptions about state shape or action schemas
- Changes to store.py, session.py, or db.py (concurrency-critical)
- Anything that touches the append-only invariant
- Protocol changes to engine.Game
-->

## Test plan

- [ ] `uv run pytest -q` passes
- [ ] `prek run --all-files` is clean (ruff + ty)
- [ ] Manually exercised the affected screens/games
- <!-- anything else reviewers should run -->

## Screenshots / recordings

<!-- Optional but appreciated for UI work. asciinema links also welcome. -->

## Checklist

- [ ] If a new game was added: registered in `src/tuimanji/games/__init__.py`
      and has a test module under `tests/`.
- [ ] If the CLI changed: README and `docs/` updated.
- [ ] If the database schema changed: explain the migration story in the
      description (the current assumption is dev-only; no migrations yet).
- [ ] CHANGELOG.md has an entry under `[Unreleased]`.
