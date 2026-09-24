"""The register-check command line.

    register-check                 # all applicable controls
    register-check run --tier 1    # subset
    register-check run --control SEC-001   # one control, as a gate verifies itself
    register-check schema          # validate controls.yaml itself
    register-check meta GOV-001    # one meta-control
    register-check assert <name>   # one command assert
    register-check explain SEC-001 # what it checks, why, and the standard it cites
    register-check deployments     # which gates are deployed here, and which are owed

Exit codes for a run, per ADR 0016:

    0  every applicable control was verified, and none is violated
    1  at least one verified violation
    2  usage error, or a target that is not a repository
    3  no violation found, but at least one applicable control could not be
       verified — a missing tool, or a remote block with no credentials

`--format json` prints the same report as data for `run` and `deployments`
(ADR 0056). It never changes an exit code.

`--require-complete` promotes 3 to 1, for the pipeline that must be
authoritative. A predicate skip is not incompleteness: a repo with no Terraform
genuinely satisfies IAC-001's applicability, so those runs still exit 0.
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version
from pathlib import Path

from register_check.deployments import (
    BadDecisions,
    NoPlugin,
    find_plugin,
    read_decisions,
    read_inventory,
)
from register_check.deployments import build as build_deployments
from register_check.deployments import render as render_deployments
from register_check.deployments import render_json as render_deployments_json
from register_check.meta import META_CHECKS
from register_check.publish import publish
from register_check.register import Control, Register, load_register
from register_check.remote import resolve as resolve_remote
from register_check.repo import NotAGitRepository, Repo, git, require_git_repo
from register_check.report import render, render_json
from register_check.runner import Verdict, exit_code, run_command_assert, run_control
from register_check.variance import (
    Direction,
    build_variance,
    gated_configs,
    render_variance,
)
from register_check.verify_meta import run_meta_control


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="register-check",
        description="Conformance checker for the Equal Experts control register.",
    )
    # The liveness probe `register-adopt` and `register-install` both run before
    # anything else. It did not exist until Phase 4 ran the front door in a
    # repository that did not author the standard and both skills stopped on
    # `unrecognized arguments: --version` — a checker installed correctly,
    # pinned correctly, and unusable because nothing could ask it whether it was
    # there. Read from the installed distribution rather than written here: a
    # literal would be a second copy of `pyproject.toml`'s version, free to
    # drift from the tag the register pins.
    parser.add_argument(
        "--version",
        action="version",
        version=f"register-check {version('register-check')}",
        help="print the installed checker's version and exit",
    )
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(), help="repository to check (default: cwd)"
    )
    parser.add_argument(
        "--register",
        type=Path,
        default=None,
        help="path to controls.yaml (default: <repo>/controls.yaml)",
    )
    parser.add_argument(
        "--github-repo",
        metavar="OWNER/NAME",
        default=None,
        help=(
            "the GitHub repository remote checks ask about "
            "(default: inferred from the origin remote)"
        ),
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="exit 1 rather than 3 when a control could not be verified",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="how `run` and `deployments` print their report (default: text; ADR 0056)",
    )
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="run all applicable controls (the default)")
    run.add_argument("--tier", type=int, choices=(1, 2, 3), default=None)
    run.add_argument(
        "--control",
        action="append",
        metavar="ID",
        default=None,
        help="verify only this control (repeatable); the gate skills' verify step",
    )
    sub.add_parser("schema", help="validate controls.yaml itself")
    meta = sub.add_parser("meta", help="run one meta-control")
    meta.add_argument("id", metavar="GOV-NNN")
    check = sub.add_parser("assert", help="run one command assert")
    check.add_argument("name")
    explain = sub.add_parser("explain", help="what a control checks, and why")
    explain.add_argument("id", metavar="ID")
    variance = sub.add_parser(
        "variance", help="which way a change to a gated config moved"
    )
    variance.add_argument(
        "--against",
        default=None,
        metavar="REF",
        help=(
            "the revision to compare the working tree against "
            "(default: the merge base with origin's default branch, else HEAD)"
        ),
    )
    variance.add_argument(
        "--path",
        action="append",
        default=None,
        metavar="FILE",
        help=(
            "an extra config file to classify, for gated config the register's "
            "`stacks:` does not name — repeatable"
        ),
    )
    sub.add_parser(
        "publish",
        help="write the adopter-facing register, derived from this one (ADR 0048)",
    )
    deployments = sub.add_parser(
        "deployments", help="which gates are deployed here, and which are owed a re-run"
    )
    deployments.add_argument(
        "--plugin",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "the plugin root whose .claude-plugin/deploys.json declares the gates "
            "(default: $CLAUDE_PLUGIN_ROOT, then <repo>/plugins/control-register)"
        ),
    )
    deployments.add_argument(
        "--decisions",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "what this repository has deliberately not deployed "
            "(default: <repo>/deployment-decisions.yaml)"
        ),
    )
    deployments.add_argument(
        "--installed",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "the harness's plugin inventory, which says at what release each "
            "skill is installed (default: $CLAUDE_CONFIG_DIR, then "
            "~/.claude, plus plugins/installed_plugins.json)"
        ),
    )
    return parser


def _load(repo_path: Path, register_path: Path | None) -> tuple[Register | None, int]:
    path = register_path or repo_path / "controls.yaml"
    register, errors = load_register(path)
    if register is None:
        print(f"schema: {path} is not a valid register:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return None, 1
    return register, 0


def _cmd_schema(repo_path: Path, register_path: Path | None) -> int:
    register, code = _load(repo_path, register_path)
    if register is None:
        return code
    print(
        f"schema: OK — register v{register.version} (contract "
        f"{register.register_contract}), {len(register.controls)} controls, "
        f"{len(register.meta_controls)} meta-controls"
    )
    return 0


def _cmd_run(
    repo_path: Path,
    register_path: Path | None,
    tier: int | None,
    require_complete: bool,
    ids: list[str] | None = None,
    github_repo: str | None = None,
    as_json: bool = False,
) -> int:
    """A conformance run, optionally narrowed to a tier or to named controls.

    `--control` is the entry point a `gate-*` skill's verify step uses. It runs
    the control's own verify blocks through `run_control` — the same function
    the full audit calls — so a gate and the auditor cannot disagree about what
    the control means. A gate that verified itself some other way would be the
    second copy this repository exists to prevent.
    """
    register, code = _load(repo_path, register_path)
    if register is None:
        return code
    repo = Repo(repo_path)
    controls = [c for c in register.controls if tier is None or c.tier == tier]
    if ids is not None:
        wanted = list(dict.fromkeys(ids))
        known = {c.id for c in controls}
        # An id nobody defines is a usage error, never an empty green run: a
        # gate that misspells its own control would otherwise report success
        # having verified nothing, which is § A's defect with a typo for a cause.
        unknown = [i for i in wanted if i not in known]
        if unknown:
            print(
                f"no control {', '.join(unknown)} in the selected set — "
                f"known: {', '.join(sorted(known))}",
                file=sys.stderr,
            )
            return 2
        controls = [c for c in controls if c.id in wanted]
    # Resolved once for the whole run and handed to every control. Resolving
    # per block would let two blocks in one report describe different
    # repositories, and a report that does not say which repository it is about
    # is not evidence about any of them.
    remote = resolve_remote(repo, github_repo)
    results = [run_control(control, register, repo, remote) for control in controls]
    # Meta-controls audit the register as a whole, so they are not part of
    # verifying one control's deployment. Narrowing the run drops them.
    meta_results = (
        []
        if ids is not None
        else [run_meta_control(meta, register, repo, remote) for meta in register.meta_controls]
    )
    print((render_json if as_json else render)(register, results, meta_results))
    verdicts = [r.verdict for r in results] + [m[2] for m in meta_results]
    # A predicate-skipped control ran nothing, so its partial declarations say
    # nothing about this run — counting them would make exit 3 fire for controls
    # that legitimately do not apply.
    partial = any(
        block.block.partial is not None
        for result in results
        if result.verdict is not Verdict.SKIPPED_PREDICATE
        for block in result.blocks
    ) or any(
        block.partial is not None
        for meta in (register.meta_controls if ids is None else [])
        for block in meta.verify
    )
    return exit_code(verdicts, require_complete=require_complete, partial=partial)


def _cmd_meta(
    repo_path: Path,
    register_path: Path | None,
    meta_id: str,
    require_complete: bool,
    github_repo: str | None = None,
) -> int:
    register, code = _load(repo_path, register_path)
    if register is None:
        return code
    if meta_id not in META_CHECKS:
        print(
            f"unknown meta-control '{meta_id}' — known: {', '.join(sorted(META_CHECKS))}",
            file=sys.stderr,
        )
        return 2
    repo = Repo(repo_path)
    verdict, message = META_CHECKS[meta_id](register, repo, resolve_remote(repo, github_repo))
    print(f"{meta_id}: {verdict} — {message}")
    return exit_code([verdict], require_complete=require_complete)


def _cmd_assert(repo_path: Path, register_path: Path | None, name: str) -> int:
    register, code = _load(repo_path, register_path)
    if register is None:
        return code
    passed, message = run_command_assert(name, register, Repo(repo_path))
    print(f"assert {name}: {'PASS' if passed else 'FAIL'} — {message}")
    return 0 if passed else 1


def _cmd_explain(repo_path: Path, register_path: Path | None, control_id: str) -> int:
    register, code = _load(repo_path, register_path)
    if register is None:
        return code
    control = register.control(control_id)
    if control is None:
        print(f"no control '{control_id}' in the register", file=sys.stderr)
        return 2
    print(f"{control.id} — {control.title}")
    print(f"\nEnforces: {control.enforces}")
    if isinstance(control, Control):
        print(f"Standard: {control.standard.name} <{control.standard.url}>")
        print(
            f"Tier {control.tier}, rung: {control.rung}, "
            f"locus: {', '.join(control.locus)}, variance: {control.variance}"
        )
        print(f"Applies to: {', '.join(control.applies_to)}")
        print(f"Owner: {control.owner}; review by {control.review_by.isoformat()}")
        print(f"Rationale: {control.rationale_adr}")
        if control.deployed_by:
            print(f"Deployed by: {control.deployed_by}")
    else:
        print(f"\nRationale: {control.rationale}")
    print("\nVerification:")
    for block in control.verify:
        print(f"  - {block.describe()}")
    return 0


def _cmd_deployments(
    repo_path: Path,
    register_path: Path | None,
    plugin: Path | None,
    decisions: Path | None = None,
    installed: Path | None = None,
    as_json: bool = False,
) -> int:
    """Report deployment currency, gate by gate.

    Exit `0` over any number of stale or undeployed gates: staleness is
    reported and never enforced (`docs/00-concepts.md` § Notify, never
    redeploy), and a command that failed over one would be enforcing
    redeployment through the back door. Exit `1` only for a defect — a stamp
    claiming a contract the installed gate has not reached — which is the same
    thing `provenance_stamp_present` already fails a register contract for — or
    for a declination that has stopped describing reality, which from ADR 0043
    includes one whose skill is installed at a later release than it names.
    """
    register, code = _load(repo_path, register_path)
    if register is None:
        return code
    try:
        repo = Repo(repo_path)
        root = find_plugin(repo, plugin)
        report = build_deployments(
            repo,
            root,
            register,
            read_decisions(repo, decisions),
            installed=read_inventory(installed),
        )
    except NoPlugin as exc:
        print(f"deployments: {exc}", file=sys.stderr)
        return 2
    except BadDecisions as exc:
        # Louder than a missing file, because a record that cannot be read is
        # not a record of nothing: reading it that way reports every declined
        # deployment as a chore nobody got to (ADR 0042 rev 2).
        print(f"deployments: {exc}", file=sys.stderr)
        return 2
    print((render_deployments_json if as_json else render_deployments)(report, register))
    # A stale *record* fails where a stale *deployment* does not. The second is
    # a recommendation; the first is a claim that has stopped being true — an
    # expired declination is a permanent exemption wearing a reason, which is
    # what GOV-003 fails a control past its review date for.
    return 1 if report.defective or report.stale_decisions else 0


def _cmd_variance(
    repo_path: Path,
    register_path: Path | None,
    against: str | None,
    extra: list[str] | None,
) -> int:
    """Report which way each gated config moved between a revision and now.

    Exit codes are ADR 0016's vocabulary rather than a third one: `1` for a
    loosening, `3` where something could not be classified, `0` otherwise. It is
    **not** part of a conformance run — a run reports whether the repository is
    conformant now, and a direction is a fact about a change (ADR 0040).
    """
    register, code = _load(repo_path, register_path)
    if register is None:
        return code
    base = against or _default_base(repo_path)
    if not _revision_exists(repo_path, base):
        print(
            f"variance: '{base}' is not a revision in this repository — with no "
            "baseline there is no delta to classify, which is a different answer "
            "from 'nothing moved'",
            file=sys.stderr,
        )
        return 2
    repo = Repo(repo_path)
    paths = gated_configs(register, repo.present) + [(p, None) for p in extra or []]
    report = build_variance(
        lambda p: _read_at(repo_path, base, p),
        lambda p: _read_now(repo_path, p),
        register,
        paths,
    )
    print(render_variance(report, base))
    if report.direction is Direction.LOOSENING:
        return 1
    return 3 if report.direction is Direction.UNCLASSIFIED else 0


def _default_base(repo_path: Path) -> str:
    """The merge base with the remote default branch, else `HEAD`.

    `HEAD` is the fallback rather than `HEAD~1` because a repository with one
    commit has no `HEAD~1`, and a command that crashed on a fresh clone would be
    reporting on the clone rather than on the change.
    """
    for candidate in ("origin/HEAD", "origin/main", "main"):
        merge_base = git(repo_path, "merge-base", "HEAD", candidate)
        if merge_base.returncode == 0 and merge_base.stdout.strip():
            return merge_base.stdout.strip()
    return "HEAD"


def _revision_exists(repo_path: Path, ref: str) -> bool:
    return git(repo_path, "rev-parse", "--verify", f"{ref}^{{commit}}").returncode == 0


def _read_at(repo_path: Path, ref: str, rel: str) -> str | None:
    """A file's text at `ref`, or `None` if it was not a file there.

    `cat-file blob` rather than `show`: `git show <ref>:<missing>` does not
    fail, it resolves the argument as a revision and prints the commit, so a
    path that was absent came back as a commit message and got classified.
    """
    result = git(repo_path, "cat-file", "blob", f"{ref}:{rel}")
    return result.stdout if result.returncode == 0 else None


def _read_now(repo_path: Path, rel: str) -> str | None:
    path = repo_path / rel
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_path: Path = args.repo.resolve()
    register_path: Path | None = args.register
    try:
        # Only the commands that evaluate the repository need it to be one;
        # `schema` and `explain` read the register and nothing else.
        if args.command in (None, "run", "assert", "meta", "deployments", "variance"):
            require_git_repo(repo_path)
        return _dispatch(args, repo_path, register_path)
    except NotAGitRepository as exc:
        print(f"register-check: {exc}", file=sys.stderr)
        return 2


def _cmd_publish(repo_path: Path) -> int:
    """Write the adopter-facing register beside the source one (ADR 0048).

    Not part of a conformance run and never failing one. It is a build step, and
    `tests/test_published_register.py` is what makes a stale output a failure —
    the same shape as a lock file.
    """
    written = publish(repo_path)
    print(f"wrote {written.relative_to(repo_path)} — derived from controls.yaml")
    return 0


def _dispatch(args: argparse.Namespace, repo_path: Path, register_path: Path | None) -> int:
    as_json = args.format == "json"
    # A format a command cannot honour is a usage error, never a silent fall
    # back to text: a consumer parsing the output would fail on the first line
    # and learn nothing about why.
    if as_json and args.command not in (None, "run", "deployments"):
        print(
            f"register-check: --format json is not supported by {args.command!r} "
            "(only run and deployments)",
            file=sys.stderr,
        )
        return 2
    match args.command:
        case None:
            return _cmd_run(
                repo_path,
                register_path,
                None,
                args.require_complete,
                None,
                args.github_repo,
                as_json,
            )
        case "run":
            return _cmd_run(
                repo_path,
                register_path,
                args.tier,
                args.require_complete,
                args.control,
                args.github_repo,
                as_json,
            )
        case "schema":
            return _cmd_schema(repo_path, register_path)
        case "meta":
            return _cmd_meta(
                repo_path, register_path, args.id, args.require_complete, args.github_repo
            )
        case "assert":
            return _cmd_assert(repo_path, register_path, args.name)
        case "explain":
            return _cmd_explain(repo_path, register_path, args.id)
        case "deployments":
            return _cmd_deployments(
                repo_path,
                register_path,
                args.plugin,
                args.decisions,
                args.installed,
                as_json,
            )
        case "publish":
            return _cmd_publish(repo_path)
        case "variance":
            return _cmd_variance(repo_path, register_path, args.against, args.path)
    raise AssertionError(f"unhandled command {args.command!r}")


if __name__ == "__main__":
    sys.exit(main())
