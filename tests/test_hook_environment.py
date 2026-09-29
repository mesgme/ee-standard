"""The suite runs as a git hook, and a git hook is told which repository it is in.

The pre-push hook runs `uv run pytest` (TST-001). Git runs that hook with
`GIT_DIR` and `GIT_INDEX_FILE` exported, and from a linked worktree both are
absolute paths into the real repository. Every `git` a test spawns inherits
them, so `git -C <tmp_path> add -A && git commit` stages the fixture's files
into the real index and commits them onto the branch being pushed.

Reported from a real push: the branch gained a commit named `fixture`, authored
by `test@example.com`, that deleted every file in the repository.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT, make_repo


def test_a_fixture_repository_holds_what_it_was_given(tmp_path: Path) -> None:
    """Run on its own by the test below, inside the environment a hook sees."""
    make_repo(tmp_path / "fixture", {"README.md": "hello\n"})
    listed = subprocess.run(
        ["git", "-C", str(tmp_path / "fixture"), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert listed.stdout.split() == ["README.md"]


def test_the_suite_leaves_the_repository_running_it_alone(tmp_path: Path) -> None:
    """The hook's repository is untouched by the fixtures the suite builds."""
    outer = tmp_path / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(outer)], check=True)
    git_dir = outer / ".git"

    hook_env = {
        **os.environ,
        "GIT_DIR": str(git_dir),
        "GIT_INDEX_FILE": str(git_dir / "index"),
    }
    node = f"{Path(__file__).name}::test_a_fixture_repository_holds_what_it_was_given"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"tests/{node}"],
        cwd=REPO_ROOT,
        env=hook_env,
        capture_output=True,
        text=True,
        check=False,
    )

    commits = subprocess.run(
        ["git", "--git-dir", str(git_dir), "rev-list", "--all"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert commits.stdout == "", (
        f"a fixture committed into the repository the hook was run from:\n{commits.stdout}"
    )
    assert not (git_dir / "index").exists(), "a fixture staged files into the hook's index"
    assert result.returncode == 0, result.stdout + result.stderr
