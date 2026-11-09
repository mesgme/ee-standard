"""Shared fixtures: throwaway git repositories and minimal valid registers."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from register_check.register import Register, load_register
from register_check.remote import CI_VARIABLE, TOKEN_VARIABLES, GitHub
from register_check.repo import Repo

REPO_ROOT = Path(__file__).resolve().parent.parent

# The pre-push hook runs this suite (TST-001), and git runs a hook with
# `GIT_DIR` and `GIT_INDEX_FILE` pointing at the repository being pushed — from
# a linked worktree, as absolute paths. Every `git` a test spawns inherits them,
# so a fixture's `git -C <tmp_path> commit` lands on the branch being pushed.
# Git names the variables that locate a repository; none of them may reach a
# test. Cleared for the whole process rather than per test, because a fixture
# of any scope can build a repository.
for _variable in subprocess.run(
    ["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True, check=True
).stdout.split():
    os.environ.pop(_variable, None)


@pytest.fixture(autouse=True)
def _no_ambient_github_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test's verdict may depend on who is logged in, or on where it runs.

    A remote block reads `GITHUB_TOKEN` from the environment, and both this
    devcontainer and GitHub Actions set one. Without this fixture the same test
    would report SKIPPED (no credentials) on a laptop and reach the network in
    CI — a suite whose results depend on ambient authentication, which is the
    kind of hidden input the checker exists to refuse. Tests that want
    credentials pass them explicitly.

    `GITHUB_ACTIONS` goes with them, from register contract 23. SEC-003's remote
    block answers only inside an Actions job, so a test that did not set the
    variable would take one branch on a laptop and the other in CI — the same
    hidden input wearing a different name.
    """
    for name in (*TOKEN_VARIABLES, CI_VARIABLE):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_ambient_plugin_inventory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Nor on which plugins happen to be installed on the machine running it.

    From ADR 0043 a declination is reconciled against the harness's plugin
    inventory, which this devcontainer has and CI does not. Left ambient, a test
    declining `lint-md@1.0.6` would pass in CI and fail on a laptop the day
    somebody updated a plugin — the same hidden input as the token above, and
    harder to spot because nothing in the test mentions it.

    Pointed at an empty directory rather than deleted, so the default branch
    (`~/.claude`) is never reached from a test at all. Tests that care about the
    inventory pass one explicitly.
    """
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-claude-config"))


class FakeGitHub(GitHub):
    """A GitHub whose answers are supplied rather than fetched."""

    def __init__(
        self,
        responses: dict[str, Any],
        slug: str = "acme/widget",
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(slug=slug, token="t")
        object.__setattr__(self, "_responses", responses)
        object.__setattr__(self, "_headers", headers or {})

    def get(self, path: str) -> Any:
        answer = self._responses[path]  # type: ignore[attr-defined]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def headers(self, path: str) -> Mapping[str, str]:
        answer: Mapping[str, str] = self._headers  # type: ignore[attr-defined]
        return answer


def requires_tool(name: str) -> pytest.MarkDecorator:
    """Skip a test whose subject is a real binary's verdict, when it is absent.

    The companion to `_no_ambient_github_token` above, for the other hidden
    input. A `kind: command` block runs an external tool and the exit code is
    the verdict, so a test asserting PASS is asserting something about a binary
    on PATH — and with the binary missing the checker correctly reports
    UNCLASSIFIED (ADR 0016), which reads as a test failure for a reason that has
    nothing to do with what the test is about.

    That is not hypothetical: `support-floor.yml` installs uv and nothing else,
    because its subject is the interpreter, and these two tests failed there
    over an absent `gitleaks` while passing on both interpreters. Declaring the
    dependency is what makes the suite say which of the two happened.

    Skipping rather than tolerating UNCLASSIFIED: a test that accepted it would
    keep passing in the devcontainer if the tool disappeared, which is the
    silence-reading-as-agreement shape this repository keeps finding.
    """
    return pytest.mark.skipif(
        shutil.which(name) is None,
        reason=f"{name} is not on PATH — this test asserts a verdict that binary produces",
    )


def make_repo(root: Path, files: dict[str, str], commit: bool = True) -> Repo:
    """A throwaway git repository holding `files`."""
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    if commit:
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "fixture",
            ],
            check=True,
        )
    return Repo(root)


def gate_contract(gate: str) -> str:
    """The deployment contract the installed plugin declares for one gate.

    Read rather than written down, for the reason ADR 0038 gives for the field
    existing at all: the number has one home, and a test that repeated it would
    keep passing over a bump nobody carried into the templates.
    """
    sidecar = json.loads(
        (REPO_ROOT / "plugins/control-register/.claude-plugin/deploys.json").read_text(
            encoding="utf-8"
        )
    )
    return str(sidecar["gates"][gate]["contractVersion"])


@pytest.fixture
def real_repo() -> Repo:
    return Repo(REPO_ROOT)


def editor_settings(
    extension: str,
    language: str = "python",
    setting: str = "editor.defaultFormatter",
) -> str:
    """`.vscode/settings.json` binding a language to the extension that holds it.

    From contract 21 a conformant repository states this, so a fixture standing
    for one has to (ADR 0029 points 3 and 4). The defaults mirror the register's
    `stacks.python.gates.lint.editor_binding`; a fixture that varies the gate
    varies these with it, which is what keeps "only the register moved" true of
    the tests that mandate a different linter.
    """
    return json.dumps({f"[{language}]": {setting: extension}}) + "\n"


def a_register() -> Register:
    """This repository's own register, for asserts that read register facts.

    Asserts take the register from contract 3 — a rule that decides a verdict
    belongs there (ADR 0018), so an assert with no register would have nowhere
    to read the rule from. Most asserts ignore it; the ones that do not
    (lockfiles, Dependabot ecosystems, tool versions) want the real definitions
    rather than a fixture that could drift from them.
    """
    register, errors = load_register(REPO_ROOT / "controls.yaml")
    assert register is not None, errors
    return register


MINIMAL_CONTROL: dict[str, Any] = {
    "id": "SEC-001",
    "title": "A commit containing a secret cannot reach the remote",
    "enforces": "gitleaks runs as a pre-commit hook.",
    "standard": {"name": "OWASP", "url": "https://example.com/standard"},
    "tier": 1,
    "rung": "blocking",
    "locus": ["pre-commit", "ci"],
    "applies_to": ["always"],
    "verify": [{"kind": "file", "assert": "precommit_hook_present", "args": {"id": "gitleaks"}}],
    "owner": "platform-engineering",
    "variance": "forbidden",
    "baseline": None,
    "review_by": "2999-01-01",
    "rationale_adr": "docs/adr/0001-test.md",
}

MINIMAL_REGISTER: dict[str, Any] = {
    "version": "0.1.0",
    "meta": {"owner": "platform-engineering", "register_contract": 1},
    "predicates": {"always": True, "python": "pyproject.toml exists"},
    "controls": [MINIMAL_CONTROL],
    "meta_controls": [
        {
            "id": "GOV-003",
            "title": "No control is past its review date",
            "enforces": "No review_by is earlier than today.",
            "rationale": "Expiry forces the re-decision.",
            "verify": [{"kind": "command", "run": "register-check meta GOV-003"}],
        }
    ],
}


def write_register(root: Path, register: dict[str, Any] | None = None) -> Path:
    """Write a register (default: the minimal valid one) plus its ADR file."""
    document = copy.deepcopy(register if register is not None else MINIMAL_REGISTER)
    root.mkdir(parents=True, exist_ok=True)
    adr = root / "docs/adr/0001-test.md"
    adr.parent.mkdir(parents=True, exist_ok=True)
    adr.write_text("# ADR 0001: Test\n", encoding="utf-8")
    path = root / "controls.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def register_with(tmp_path: Path, mutate: Any) -> Register:
    """This repository's register with one edit applied, reloaded from disk.

    The shape every "only the register moved" test needs: the checker is
    untouched, one field of `controls.yaml` changes, and the verdict has to
    change with it. An assert still holding the rule privately passes the
    happy path and fails here.
    """
    document = yaml.safe_load((REPO_ROOT / "controls.yaml").read_text(encoding="utf-8"))
    mutate(document)
    root = tmp_path / "register"
    root.mkdir(parents=True, exist_ok=True)
    (root / "controls.yaml").write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    # `rationale_adr` paths are checked relative to the register, so bring them.
    # A citation is a URL from register contract 30 and resolves to no file at
    # all; creating one would write a directory named `https:` beside the
    # register and prove nothing.
    for control in document["controls"] + document.get("meta_controls", []):
        adr = control.get("rationale_adr")
        if adr and not str(adr).startswith(("http://", "https://")):
            target = root / adr
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# ADR\n", encoding="utf-8")
    register, errors = load_register(root / "controls.yaml")
    assert register is not None, errors
    return register


def minimal_register(**overrides: Any) -> dict[str, Any]:
    """A deep copy of the minimal register with control-level overrides applied."""
    document = copy.deepcopy(MINIMAL_REGISTER)
    document["controls"][0].update(overrides)
    return document
