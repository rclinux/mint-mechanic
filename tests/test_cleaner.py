"""Cleaner task definitions — above all, that the fixed shell commands stay
correctly quoted.

These commands are interpolated with the user's home directory and run through
`bash -c`. Before the quoting fix, a home directory containing a space
word-split `rm -rf $HOME/.cache/thumbnails/*` into an rm against a *different,
shorter path* — a wrong-path delete, not a harmless failure. Each command is
re-parsed with shlex here to prove the paths survive as single tokens.
"""

import importlib
import shlex

import pytest

import ltt.cleaner as cleaner


def reload_with_home(monkeypatch, home):
    """Re-import the module as if $HOME were `home` (paths bind at import)."""
    monkeypatch.setenv("HOME", home)
    monkeypatch.setattr("os.path.expanduser", lambda p: p.replace("~", home, 1))
    return importlib.reload(cleaner)


@pytest.fixture(autouse=True)
def restore_module():
    yield
    importlib.reload(cleaner)


AWKWARD_HOMES = [
    "/home/jane doe",        # space — the original bug
    "/home/o'brien",         # single quote — defeats Python's !r
    "/home/user (backup)",   # shell metacharacters
    "/home/plain",           # control case
]


@pytest.mark.parametrize("home", AWKWARD_HOMES)
def test_thumbnail_command_keeps_the_path_intact(monkeypatch, home):
    mod = reload_with_home(monkeypatch, home)
    task = next(t for t in mod.tasks() if t.key == "thumbnails")
    tokens = shlex.split(task.command)
    assert tokens[0] == "rm"
    # The glob is unexpanded by shlex, but the directory must be one token.
    assert tokens[-1] == f"{home}/.cache/thumbnails/*"


@pytest.mark.parametrize("home", AWKWARD_HOMES)
def test_trash_command_keeps_every_path_intact(monkeypatch, home):
    mod = reload_with_home(monkeypatch, home)
    task = next(t for t in mod.tasks() if t.key == "trash")
    trash = f"{home}/.local/share/Trash"
    tokens = shlex.split(task.command)
    for sub in ("files", "info", "expunged"):
        assert f"{trash}/{sub}" in tokens
    assert f"{trash}/directorysizes" in tokens


@pytest.mark.parametrize("home", AWKWARD_HOMES)
def test_no_command_can_target_a_truncated_path(monkeypatch, home):
    """The failure mode itself: a path prefix appearing as its own token."""
    mod = reload_with_home(monkeypatch, home)
    truncated = home.split(" ")[0]
    if truncated == home:
        pytest.skip("no split point in this home path")
    for task in mod.tasks():
        assert truncated not in shlex.split(task.command)


def test_du_quotes_its_argument(monkeypatch):
    seen = {}
    monkeypatch.setattr(cleaner, "_sh", lambda cmd: seen.setdefault("cmd", cmd) or "4.0K")
    monkeypatch.setattr("os.path.exists", lambda p: True)
    cleaner._du("/home/jane doe/.local/share/Trash")
    assert "/home/jane doe/.local/share/Trash" in shlex.split(seen["cmd"])


def test_du_reports_empty_for_a_missing_path(monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda p: False)
    assert cleaner._du("/nonexistent") == "empty"


# ------------------------------------------------------------------ sizing
@pytest.mark.parametrize("n,expected", [
    (0, "0B"),
    (512, "512B"),
    (1024, "1.0K"),
    (1536, "1.5K"),
    (1024 ** 2, "1.0M"),
    (1024 ** 3, "1.0G"),
    (1024 ** 4, "1.0T"),
])
def test_human_readable_sizes(n, expected):
    assert cleaner._human(n) == expected


def test_content_size_sums_file_bytes(monkeypatch):
    monkeypatch.setattr(cleaner, "_sh", lambda cmd: "100\n200\n300\n")
    assert cleaner._content_size("find ...") == "600B"


def test_content_size_reads_empty_not_the_directory_overhead(monkeypatch):
    """The ext4 quirk this measurement exists to avoid: a cleared area must
    read 'empty', not the KBs of an emptied-but-unshrunk directory inode."""
    monkeypatch.setattr(cleaner, "_sh", lambda cmd: "")
    assert cleaner._content_size("find ...") == "empty"


def test_sh_never_raises_on_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("no bash")
    monkeypatch.setattr(cleaner.subprocess, "run", boom)
    assert cleaner._sh("true") == ""


# ------------------------------------------------------------------- tasks
def test_root_tasks_are_marked_for_elevation():
    by_key = {t.key: t for t in cleaner.tasks()}
    assert by_key["apt_cache"].root is True
    assert by_key["orphans"].root is True
    assert by_key["journal"].root is True
    assert by_key["thumbnails"].root is False
    assert by_key["trash"].root is False


def test_trash_is_the_last_user_task():
    """Ordering is deliberate: Trash goes last so it also catches anything the
    earlier tasks discarded during the same run.

    CleanerView is what enforces this at run time (it sorts user tasks with
    `key == "trash"` last, and runs the root batch before any user task). This
    pins the declaration order as defence in depth, so the two can't drift.
    """
    user_keys = [t.key for t in cleaner.tasks() if not t.root]
    assert user_keys[-1] == "trash"


def test_trash_sort_key_forces_it_last():
    """The exact ordering rule CleanerView applies, without importing GTK."""
    user_tasks = [t for t in cleaner.tasks() if not t.root]
    ordered = sorted(user_tasks, key=lambda t: t.key == "trash")
    assert ordered[-1].key == "trash"


def test_every_task_measure_returns_a_string():
    for task in cleaner.tasks():
        assert isinstance(task.measure(), str)
