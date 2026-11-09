"""`--format json` — the same verdicts, readable by something other than a person.

A consumer outside this repository (a fleet sweep keeping verdict history) needs
the report as data. The risk is a second report: a JSON renderer that computes
its own verdicts, counts or exit code would be free to disagree with the text
one, and the reader would have no way to know which to believe. So everything
here is a comparison against the text report of the same run, never a fixture
of what the JSON "should" say.
"""

from __future__ import annotations

import json
import re
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest

from conftest import make_repo, minimal_register, write_register
from register_check.cli import main

_HOOKS = "repos:\n  - repo: local\n    hooks:\n      - id: gitleaks\n"


def _two_control_register() -> dict[str, Any]:
    """The minimal register plus a second, deliberately failing, control."""
    document = minimal_register()
    document["controls"].append(
        dict(
            document["controls"][0],
            id="LNT-001",
            title="A control this repo violates",
            verify=[
                {"kind": "file", "assert": "precommit_hook_present", "args": {"id": "ruff"}}
            ],
        )
    )
    return document


def _both(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], *args: str
) -> tuple[int, str, int, dict[str, Any]]:
    """Run once as text and once as JSON; return both exits and both outputs."""
    text_exit = main(["--repo", str(tmp_path), *args])
    text = capsys.readouterr().out
    json_exit = main(["--repo", str(tmp_path), "--format", "json", *args])
    document = json.loads(capsys.readouterr().out)
    return text_exit, text, json_exit, document


@pytest.fixture
def failing_repo(tmp_path: Path) -> Path:
    write_register(tmp_path, _two_control_register())
    make_repo(tmp_path, {".pre-commit-config.yaml": _HOOKS})
    return tmp_path


def test_the_format_does_not_change_the_exit_code(
    failing_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR 0016's exit codes belong to the verdicts, not to how they are printed."""
    text_exit, _, json_exit, _ = _both(failing_repo, capsys, "run")
    assert text_exit == json_exit == 1


def test_the_document_says_what_produced_it(
    failing_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A verdict kept for later is evidence only alongside what decided it."""
    _, text, _, document = _both(failing_repo, capsys, "run")
    assert document["format"] == 1
    assert document["checker_version"] == version("register-check")
    header = re.search(r"register v(\S+) \(contract (\d+)\)", text)
    assert header is not None, text
    assert document["register_version"] == header.group(1)
    assert document["register_contract"] == int(header.group(2))


def test_every_control_carries_the_verdict_the_text_report_gives(
    failing_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, text, _, document = _both(failing_repo, capsys, "run")
    by_id = {c["id"]: c for c in document["controls"]}
    assert set(by_id) == {"SEC-001", "LNT-001"}
    for control_id, control in by_id.items():
        line = re.search(rf"^  {control_id}\s+(.+?)\s{{2,}}", text, re.MULTILINE)
        assert line is not None, text
        assert control["verdict"] == line.group(1)
        assert {"tier", "rung", "title", "note", "blocks"} <= control.keys()


def test_a_failing_control_carries_its_reason(
    failing_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A FAIL without the block that failed would be a verdict nobody can act on."""
    _, _, _, document = _both(failing_repo, capsys, "run")
    (failing,) = [c for c in document["controls"] if c["id"] == "LNT-001"]
    assert failing["verdict"] == "FAIL"
    (block,) = failing["blocks"]
    assert block["verdict"] == "FAIL"
    assert "ruff" in block["message"]
    assert block["describe"]


def test_the_summary_counts_are_the_text_report_s(
    failing_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, text, _, document = _both(failing_repo, capsys, "run")
    summary = document["summary"]
    assert f"{summary['passed']} passed" in text
    assert f"{summary['failed']} failed" in text
    assert f"{summary['unclassified']} unclassified" in text
    assert f"meta-controls: {summary['meta_passed']}/{summary['meta_total']} passed" in text


def test_meta_controls_are_reported_and_a_narrowed_run_has_none(
    failing_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, text, _, document = _both(failing_repo, capsys, "run")
    assert document["meta"], "a full run audits the register too"
    for meta in document["meta"]:
        assert meta["id"] in text
        assert {"title", "verdict", "message"} <= meta.keys()

    _, _, _, narrowed = _both(failing_repo, capsys, "run", "--control", "SEC-001")
    assert narrowed["meta"] == []


def test_text_stays_the_default(
    failing_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every locus that already runs the checker reads text, and must keep doing so."""
    main(["--repo", str(failing_repo), "run"])
    out = capsys.readouterr().out
    assert out.startswith("control register conformance report")


def test_a_command_that_cannot_honour_the_format_says_so(
    failing_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Never a silent fall back to text: a parser would fail on line one and learn nothing."""
    assert main(["--repo", str(failing_repo), "--format", "json", "schema"]) == 2
    assert "--format json is not supported by 'schema'" in capsys.readouterr().err
