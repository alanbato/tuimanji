"""Pubnix / shared-host permission propagation.

When the data dir is set up sticky+world-writable (mode 1777, like /tmp),
files and subdirs we create inside it must inherit those perms or another
user on the box can't read/write them. These tests pin that contract.
"""

import os
import stat

import pytest

from tuimanji.db import (
    _make_engine,
    _reset_engine,
    db_dir,
    is_shared_dir,
    propagate_shared_perms,
)
from tuimanji.session import _sessions_dir


@pytest.fixture
def shared_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIMANJI_DB", str(tmp_path))
    os.chmod(tmp_path, 0o1777)
    _reset_engine()
    return tmp_path


@pytest.fixture
def private_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TUIMANJI_DB", str(tmp_path))
    os.chmod(tmp_path, 0o755)
    _reset_engine()
    return tmp_path


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_is_shared_dir_true_for_sticky_world_writable(tmp_path):
    os.chmod(tmp_path, 0o1777)
    assert is_shared_dir(tmp_path)


def test_is_shared_dir_false_without_sticky(tmp_path):
    os.chmod(tmp_path, 0o777)
    assert not is_shared_dir(tmp_path)


def test_is_shared_dir_false_when_not_world_writable(tmp_path):
    os.chmod(tmp_path, 0o755)
    assert not is_shared_dir(tmp_path)


def test_propagate_chmods_dir_to_1777(shared_db):
    child = shared_db / "sub"
    child.mkdir(mode=0o755)
    propagate_shared_perms(child, shared_db)
    assert _mode(child) == 0o1777


def test_propagate_chmods_file_to_666(shared_db):
    child = shared_db / "f"
    child.write_text("x")
    os.chmod(child, 0o644)
    propagate_shared_perms(child, shared_db)
    assert _mode(child) == 0o666


def test_propagate_noop_on_private_parent(private_db):
    child = private_db / "sub"
    child.mkdir(mode=0o755)
    propagate_shared_perms(child, private_db)
    assert _mode(child) == 0o755


def test_sessions_dir_inherits_shared_perms(shared_db):
    _sessions_dir("alice")
    assert _mode(shared_db / ".sessions") == 0o1777


def test_sessions_dir_stays_private_on_private_parent(private_db):
    _sessions_dir("alice")
    # Default 0o755 from mkdir under typical 0o022 umask. We only assert the
    # sticky+world-writable bits aren't on, since umask varies by environment.
    sessions_mode = _mode(private_db / ".sessions")
    assert not (sessions_mode & 0o1000) or not (sessions_mode & 0o002)


def test_db_file_chmodded_when_shared(shared_db):
    _make_engine()  # creates tuimanji.db via SQLModel.metadata.create_all
    assert _mode(shared_db / "tuimanji.db") == 0o666


def test_db_file_left_alone_when_private(private_db):
    _make_engine()
    db_file = private_db / "tuimanji.db"
    # We only care that we didn't open it up — exact mode follows umask.
    assert not (_mode(db_file) & 0o002)


def test_db_dir_resolves_under_shared_root(shared_db):
    assert db_dir() == shared_db
    assert is_shared_dir(db_dir())
