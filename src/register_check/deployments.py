"""Which gates are deployed in a repository, and which are owed a redeployment.

The register says what conformant means; the plugin's `.claude-plugin/deploys.json`
says which gate writes which artefact and at what **deployment contract**; the
`ee-control:` stamps in the repository say what was actually written. This module
is the join, and it is the reader ADR 0038 added the stamp's `gate-contract`
field for.

The whole point is the noise argument (`docs/02-skill-family.md` § Staleness): a
gate's *version* moves for documentation fixes and trigger-phrase tweaks, and
recommending a redeployment on one of those trains everyone to ignore the
recommendation. A gate's *contract* moves only when what it writes changes. So
nothing here compares versions.

Staleness is **reported, never enforced** (`docs/00-concepts.md` § Notify, never
redeploy). Nothing in this module fails a build over a gate that is behind — the
verdict for that is a recommendation. What does fail is a *defect*: a stamp
claiming a contract the installed gate has not reached, which is a deployment
ahead of the thing it deploys.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from importlib.metadata import version as installed_version
from pathlib import Path

import yaml

from register_check.provenance import stamps_by_file
from register_check.register import Control, Register
from register_check.repo import Repo
from register_check.report import JSON_FORMAT
from register_check.runner import applies

#: The sidecar's shape this code understands. A file declaring anything else is
#: an error rather than a best-effort read: guessing at an unknown layout is how
#: a reader reports "never deployed" over a repository that is fully deployed.
SCHEMA_VERSION = 2

#: Where the plugin lives when nothing says otherwise. `CLAUDE_PLUGIN_ROOT` is
#: what a skill has in hand at runtime (the spelling ADR 0036's shared reference
#: files are read through); the repository path is what this repository has,
#: where the plugin it ships and the repository it audits are the same tree.
_PLUGIN_ENV = "CLAUDE_PLUGIN_ROOT"
_PLUGIN_IN_REPO = "plugins/control-register"

_SIDECAR = ".claude-plugin/deploys.json"


class State(Enum):
    """What is known about one gate's deployment in this repository.

    `NEVER_DEPLOYED`, `CURRENT` and `STALE` are Phase 5's criterion that a
    repository which has never deployed is distinguishable from one deployed
    and current and from one deployed and stale. The other three exist because
    collapsing them into those would state something false: `UNRECORDED` is not
    "current", `AHEAD` is not "stale", and a gate whose controls do not apply to
    this repository is not undeployed — nothing is owed. A predicate skip is not
    a gap (`docs/00-concepts.md` § Predicates), and reporting one as an act
    somebody owes is the noise this whole mechanism exists to avoid.
    """

    NOT_APPLICABLE = "NOT APPLICABLE"
    NEVER_DEPLOYED = "NEVER DEPLOYED"
    UNRECORDED = "UNRECORDED"
    STALE = "STALE"
    CURRENT = "CURRENT"
    AHEAD = "AHEAD"

    def __str__(self) -> str:
        return self.value


#: Where a repository records what it deliberately has not deployed. Beside
#: `controls.yaml` rather than inside it: a declination is posture, and ADR 0022
#: requirement 6 keeps posture out of what an adopter installs (ADR 0042 rev 2).
DECISIONS = "deployment-decisions.yaml"

#: Where the Claude Code harness records which plugins are installed, and at
#: what version. Read directly rather than through `claude plugin list`: the
#: answer lives in a JSON file, and shelling out would make a checker that has
#: the file but not the CLI unable to read it (ADR 0043 part 1).
_INVENTORY_ENV = "CLAUDE_CONFIG_DIR"
_INVENTORY_HOME = ".claude"
_INVENTORY = "plugins/installed_plugins.json"


@dataclass(frozen=True)
class Declination:
    """One release this repository has decided not to take, and until when."""

    skill: str
    version: str
    reason: str
    review_by: datetime.date
    adr: str | None = None

    def expired(self, today: datetime.date) -> bool:
        return self.review_by < today


def _version_key(version: str) -> tuple[int, ...]:
    """A dotted version as integers, for the one comparison this module makes.

    Not a semver implementation: the only question asked is whether a declined
    release is one this repository has already moved past, and a version that
    does not parse simply never answers yes — which reports nothing rather than
    reporting something invented.
    """
    pieces = version.split(".")
    if not all(piece.isdigit() for piece in pieces):
        return ()
    return tuple(int(piece) for piece in pieces)


@dataclass(frozen=True)
class Inventory:
    """What the harness reports as installed, or why that could not be read.

    Two fields rather than one dictionary, because *nothing installed* and
    *nothing readable* are different answers and collapsing them is the bug
    ADR 0043 part 2 is about: a missing inventory would read as "no skill is
    newer than any declination", which is agreement invented out of not having
    looked.
    """

    versions: dict[str, str]
    #: Why `versions` is empty, when it is empty for a reason. `None` means the
    #: inventory was read and simply lists nothing relevant.
    unreadable: str | None = None

    def version_of(self, skill: str) -> str | None:
        return self.versions.get(skill)


def read_inventory(path: Path | None = None) -> Inventory:
    """The installed version of every plugin the harness knows about.

    Never raises. A checker that failed because a developer's home directory
    is laid out unusually would be failing over the one input it is allowed
    not to have — CI has no plugins installed at all, and that run must still
    produce a report.
    """
    target = path or _inventory_path()
    if not target.is_file():
        return Inventory({}, f"no plugin inventory at {target}")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Inventory({}, f"{target} could not be read: {exc}")
    plugins = raw.get("plugins") if isinstance(raw, dict) else None
    if not isinstance(plugins, dict):
        return Inventory({}, f"{target} declares no plugins")
    versions: dict[str, str] = {}
    for key, installs in plugins.items():
        # `lint-md@ee-skills` — the marketplace is the suffix, and the skill is
        # what a provenance stamp names.
        name = str(key).rsplit("@", 1)[0]
        if not isinstance(installs, list):
            continue
        for install in installs:
            if not isinstance(install, dict):
                continue
            version = install.get("version")
            if not isinstance(version, str):
                continue
            # Installed at two scopes: the later one wins. A record covering
            # the older of two installations is covering the copy that is not
            # going to run (ADR 0043 part 1).
            current = versions.get(name)
            if current is None or _version_key(version) > _version_key(current):
                versions[name] = version
    return Inventory(versions)


def _inventory_path() -> Path:
    """`$CLAUDE_CONFIG_DIR` beats `~/.claude`, which is the harness's own default."""
    configured = os.environ.get(_INVENTORY_ENV)
    root = Path(configured) if configured else Path.home() / _INVENTORY_HOME
    return root / _INVENTORY


def read_decisions(repo: Repo, path: Path | None = None) -> tuple[Declination, ...]:
    """The declinations on record, or an error if the file cannot be read.

    A malformed file raises rather than returning nothing. Silently reading it
    as "no declinations" reports every declined deployment as a chore nobody got
    to, which is the exact opposite of what the record says — and the failure
    would be invisible, because the report would look ordinary.
    """
    target = path or repo.root / DECISIONS
    if not target.exists():
        return ()
    try:
        document = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BadDecisions(f"{target} is not valid YAML: {exc}") from exc
    if document is None:
        return ()
    if not isinstance(document, dict):
        raise BadDecisions(f"{target} must be a mapping with a 'declined' key")
    entries = document.get("declined") or []
    if not isinstance(entries, list):
        raise BadDecisions(f"{target}: 'declined' must be a list")
    found: list[Declination] = []
    for i, entry in enumerate(entries):
        at = f"{target}: declined[{i}]"
        if not isinstance(entry, dict):
            raise BadDecisions(f"{at} must be a mapping")
        missing = [k for k in ("skill", "version", "reason", "review_by") if k not in entry]
        if missing:
            raise BadDecisions(f"{at} is missing: {', '.join(missing)}")
        review_by = entry["review_by"]
        if isinstance(review_by, str):
            try:
                review_by = datetime.date.fromisoformat(review_by)
            except ValueError as exc:
                raise BadDecisions(f"{at}.review_by is not an ISO date") from exc
        if not isinstance(review_by, datetime.date):
            raise BadDecisions(f"{at}.review_by must be an ISO date")
        found.append(
            Declination(
                skill=str(entry["skill"]),
                version=str(entry["version"]),
                reason=" ".join(str(entry["reason"]).split()),
                review_by=review_by,
                adr=str(entry["adr"]) if entry.get("adr") else None,
            )
        )
    return tuple(found)


def decision_problems(
    declined: tuple[Declination, ...],
    deployed: dict[str, str],
    today: datetime.date,
    installed: Inventory | None = None,
) -> list[str]:
    """What is wrong with the record itself, as opposed to with a deployment.

    Three things, and each is a record that has stopped describing reality
    rather than a deployment anyone owes:

    An **expired** entry is a decision nobody has revisited. GOV-003 fails a
    control past its review date for the same reason, and a declination is a
    stronger claim than a control: it says a release should not be taken.

    A declination for a version this repository has **already deployed** is a
    record of a decision that no longer applies — the stamp moved past it.

    A declination naming a skill **nothing here stamps** describes a deployment
    that does not exist, which is a record nobody could act on.

    And a declination whose skill is **installed at a later release** has
    stopped covering that skill (ADR 0043). `deployment-decisions.yaml` says so
    in its own header and the report prints the rule underneath every entry;
    until this was added, nothing applied it, so a record went quiet about the
    release it was no longer speaking for.
    """
    problems: list[str] = []
    for entry in declined:
        if entry.expired(today):
            problems.append(
                f"{entry.skill}@{entry.version}: declined until {entry.review_by} and that "
                "date has passed — a declination nobody has revisited is a permanent "
                "exemption wearing a reason"
            )
        stamped = deployed.get(entry.skill)
        if stamped is None:
            problems.append(
                f"{entry.skill}@{entry.version}: nothing in this repository carries a stamp "
                f"naming '{entry.skill}', so the record describes a deployment that does "
                "not exist"
            )
        elif _both_parse_and_stamp_is_newer(stamped, entry.version):
            problems.append(
                f"{entry.skill}@{entry.version}: already deployed at {stamped}, so the "
                "decision no longer applies and the entry should go"
            )
        here = (installed or Inventory({})).version_of(entry.skill)
        if here is not None and _is_later(here, entry.version):
            problems.append(
                f"{entry.skill}@{entry.version}: {entry.skill} is installed at {here}, "
                "which this record does not cover — a declination covers the version it "
                "names and no later one, so the question is re-opened and the entry must "
                "be renewed against the new release or deleted"
            )
    return problems


def unreconciled(
    declined: tuple[Declination, ...],
    installed: Inventory,
) -> list[str]:
    """Declinations whose installed release could not be determined, and why.

    Reported rather than counted as agreement, and separately from
    `decision_problems` because it is not a problem with the record: it is this
    run saying which question it did not get to answer (ADR 0043 part 2). CI has
    no plugins installed, so this is the ordinary case there rather than a fault.
    """
    notes: list[str] = []
    for entry in declined:
        here = installed.version_of(entry.skill)
        if here is None:
            why = installed.unreadable or f"{entry.skill} is not installed here"
            notes.append(f"{entry.skill}@{entry.version}: {why}")
        elif not (_version_key(here) and _version_key(entry.version)):
            notes.append(
                f"{entry.skill}@{entry.version}: installed at {here}, which does not "
                "compare as a dotted version"
            )
    return notes


def _is_later(installed: str, declined: str) -> bool:
    """Strictly later, and only when both sides parse.

    Strictly, because a record naming the version that is installed covers it
    exactly — that is the whole state a declination is written in. Both sides,
    for `_both_parse_and_stamp_is_newer`'s reason: an unparseable version that
    sorted below everything would report a live record as superseded.
    """
    a, b = _version_key(installed), _version_key(declined)
    return bool(a) and bool(b) and a > b


def _both_parse_and_stamp_is_newer(stamped: str, declined: str) -> bool:
    """Whether the repository has demonstrably moved past the declined release.

    **Both** sides must parse. Requiring only one was a bug the tests caught
    before it shipped: an unreadable declined version returned an empty key,
    every deployed version sorted above it, and the record was reported as
    superseded — telling someone to delete a live declination.
    """
    stamped_key, declined_key = _version_key(stamped), _version_key(declined)
    return bool(stamped_key) and bool(declined_key) and stamped_key >= declined_key


#: The states that mean somebody is owed an act. `UNRECORDED` is in the list
#: because a deployment nobody can date cannot be shown to be current, and
#: reporting it as current would be a guess in the repository's favour.
OWED = (State.NEVER_DEPLOYED, State.UNRECORDED, State.STALE)


@dataclass(frozen=True)
class Gate:
    """One gate as the installed plugin declares it."""

    name: str
    contract: int
    controls: tuple[str, ...]
    artifacts: tuple[str, ...]

    @property
    def paths(self) -> tuple[str, ...]:
        """The artefact paths, with the `#anchor` that names a region dropped.

        A gate that owns three hooks in `.pre-commit-config.yaml` lists three
        artefacts at one path. What can be checked here is that the file is
        there; which region of it belongs to whom is what the per-region stamp
        already says.
        """
        return tuple(dict.fromkeys(a.split("#", 1)[0] for a in self.artifacts))


@dataclass(frozen=True)
class GateReport:
    gate: Gate
    state: State
    deployed: tuple[int | None, ...]
    stamped_paths: tuple[str, ...]
    absent_paths: tuple[str, ...]

    @property
    def behind(self) -> list[int]:
        return sorted({c for c in self.deployed if c is not None and c < self.gate.contract})


@dataclass(frozen=True)
class Report:
    plugin: Path
    gates: tuple[GateReport, ...]
    #: Stamps naming a skill this plugin does not ship — DOC-001's `lint-md` is
    #: the standing example. Not a defect and not this plugin's business, but
    #: silently dropping them would report a repository as less deployed than
    #: it is.
    foreign: tuple[tuple[str, str], ...]
    #: What this repository has decided not to deploy, and why. Read from
    #: `deployment-decisions.yaml` (ADR 0042 rev 2). An empty tuple means the
    #: file is absent — never that it could not be read, which raises.
    declined: tuple[Declination, ...] = ()
    #: Records that have stopped describing reality: expired, superseded by a
    #: deployment or by an installed release, or naming a skill nothing stamps.
    #: Distinct from `owed`, which is about deployments rather than the record.
    stale_decisions: tuple[str, ...] = ()
    #: Declinations this run could not reconcile against an installed release,
    #: each with the reason. Not a problem and not agreement — the third state
    #: ADR 0043 part 2 keeps apart from both.
    unreconciled: tuple[str, ...] = ()
    #: `source: literal` pins at sites no dependency bot is configured to
    #: propose an upgrade for. Reported here rather than failing SUP-002
    #: (`docs/17-adopter-onboarding-review.md` Decision 2): the property is real
    #: — an unmanaged pin never moves — but the check needs a `renovate.json`
    #: parser, and a Tier-1 `blocking` control is a hard place to put one before
    #: anybody knows how often it fires.
    unmanaged_pins: tuple[str, ...] = ()

    @property
    def owed(self) -> list[GateReport]:
        return [g for g in self.gates if g.state in OWED]

    @property
    def defective(self) -> list[GateReport]:
        return [g for g in self.gates if g.state is State.AHEAD]


class NoPlugin(Exception):
    """No plugin to read a deployment contract from, so nothing can be said."""


class BadDecisions(Exception):
    """The declination record cannot be read, so its absence cannot be trusted."""


def find_plugin(repo: Repo, explicit: Path | None = None) -> Path:
    """The plugin root whose `deploys.json` this run reads.

    Explicit beats environment beats repository, and none of the three is a
    fallback for a *wrong* one: a `--plugin` naming a directory with no sidecar
    raises rather than quietly moving on to the next candidate, because the
    answer to "which plugin did you mean" is never "some other one".
    """
    if explicit is not None:
        return _require_sidecar(explicit)
    from_env = os.environ.get(_PLUGIN_ENV)
    if from_env:
        return _require_sidecar(Path(from_env))
    candidate = repo.root / _PLUGIN_IN_REPO
    if (candidate / _SIDECAR).is_file():
        return candidate
    raise NoPlugin(f"no {_SIDECAR} found — pass --plugin <plugin root>, or set {_PLUGIN_ENV}")


def _require_sidecar(root: Path) -> Path:
    if not (root / _SIDECAR).is_file():
        raise NoPlugin(f"{root} ships no {_SIDECAR}")
    return root


def load_gates(plugin: Path) -> tuple[Gate, ...]:
    """The gates the installed plugin declares, in the order it declares them."""
    raw = json.loads((plugin / _SIDECAR).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise NoPlugin(f"{plugin / _SIDECAR} is not an object")
    version = raw.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise NoPlugin(
            f"{plugin / _SIDECAR} declares schemaVersion {version!r}, "
            f"and this checker reads {SCHEMA_VERSION}"
        )
    gates = raw.get("gates")
    if not isinstance(gates, dict):
        raise NoPlugin(f"{plugin / _SIDECAR} declares no gates")
    return tuple(
        Gate(
            name=name,
            contract=int(entry["contractVersion"]),
            controls=tuple(entry.get("controls", ())),
            artifacts=tuple(entry.get("artifacts", ())),
        )
        for name, entry in gates.items()
    )


def _applicable(gate: Gate, register: Register, repo: Repo) -> bool:
    """Whether any control this gate carries applies to this repository.

    Any, not all: `gate-quality` deploys three controls and a repository that
    satisfies one of them is owed the gate. A gate naming no control the
    register defines is treated as applicable — that is a defect in the
    sidecar, which `tests/test_plugin.py` holds, and swallowing it here as
    "nothing to do" would hide it.
    """
    controls = [c for c in register.controls if c.id in gate.controls]
    if not controls:
        return True
    return any(applies(c, register, repo)[0] for c in controls if isinstance(c, Control))


def _classify(gate: Gate, deployed: list[int | None], applicable: bool) -> State:
    if not deployed:
        return State.NEVER_DEPLOYED if applicable else State.NOT_APPLICABLE
    # Ahead first: a defect outranks every currency question, and a repository
    # holding one stamp ahead and one behind has a defect, not a chore.
    if any(c is not None and c > gate.contract for c in deployed):
        return State.AHEAD
    if any(c is None for c in deployed):
        return State.UNRECORDED
    if any(c is not None and c < gate.contract for c in deployed):
        return State.STALE
    return State.CURRENT


#: A `# renovate:` annotation, which is what a custom manager matches against.
#: Renovate finds a literal by regex and the regex anchors on this comment, so a
#: pin without one is not stale — it is unmanaged, and nothing will ever propose
#: moving it.
_RENOVATE_ANNOTATION = re.compile(r"^\s*#\s*renovate:\s*datasource=", re.MULTILINE)

#: Where a repository may configure Renovate. Dependabot is not consulted: it
#: has no custom manager, which is the whole reason this check exists.
_RENOVATE_CONFIGS = (
    "renovate.json",
    "renovate.json5",
    ".github/renovate.json",
    ".github/renovate.json5",
    ".renovaterc",
    ".renovaterc.json",
)


def unmanaged_literal_pins(repo: Repo, register: Register) -> tuple[str, ...]:
    """`source: literal` pins that no bot is configured to propose an upgrade for.

    Two conditions, and both must hold before anything is reported. The
    repository has no Renovate configuration at all, **or** a `pinned_at` site
    carries no `# renovate:` annotation — in either case the version sitting
    there is one nothing will move.

    This is a *report*, never a verdict. `docs/17-adopter-onboarding-review.md`
    § J is the finding it comes from: the shipped devcontainer template puts
    `UV_VERSION="..."` in a shell script, which is exactly the case Dependabot
    has no manager for, so every adopter of that template has at least one such
    pin and SUP-002 stays green over it. Failing the control was considered and
    deferred (Decision 2) — this exists to measure how often it happens before
    anyone decides whether a Tier-1 control should refuse it.

    A repository whose register pins no literal tool gets an empty tuple and no
    line in the report, which is the right answer rather than a silence.
    """
    literal = [t for t in register.tools.values() if t.source == "literal"]
    if not literal:
        return ()
    configured = any(repo.exists(path) for path in _RENOVATE_CONFIGS)
    findings: list[str] = []
    for tool in literal:
        for path in tool.pinned_at:
            if not repo.exists(path):
                continue  # a declared site that is absent is SUP-004's finding
            if not configured:
                findings.append(
                    f"{tool.name} at {path} — no Renovate configuration in this "
                    "repository, and Dependabot has no manager for a literal"
                )
            elif not _RENOVATE_ANNOTATION.search(repo.read(path)):
                findings.append(
                    f"{tool.name} at {path} — no `# renovate:` annotation, so no "
                    "custom manager matches this pin"
                )
    return tuple(findings)


def build(
    repo: Repo,
    plugin: Path,
    register: Register,
    declined: tuple[Declination, ...] = (),
    today: datetime.date | None = None,
    installed: Inventory | None = None,
) -> Report:
    """Read the sidecar and the repository's stamps, and join them.

    The register is the third input, and it is here for the same reason the
    runner resolves a remote target once for a whole run: applicability is a
    register question, and a gate whose controls this repository's files do not
    satisfy is owed nothing. Asking it here rather than in the report keeps one
    answer per run.
    """
    gates = load_gates(plugin)
    stamps = stamps_by_file(repo)
    unmanaged = unmanaged_literal_pins(repo, register)
    known = {gate.name for gate in gates}
    reports = []
    for gate in gates:
        deployed: list[int | None] = []
        paths: list[str] = []
        for path, in_file in stamps.items():
            mine = [s for s in in_file if s.skill == gate.name]
            if mine:
                paths.append(path)
                deployed.extend(s.gate_contract for s in mine)
        reports.append(
            GateReport(
                gate=gate,
                state=_classify(gate, deployed, _applicable(gate, register, repo)),
                deployed=tuple(deployed),
                stamped_paths=tuple(sorted(paths)),
                absent_paths=tuple(p for p in gate.paths if not repo.exists(p)),
            )
        )
    foreign = tuple(
        sorted(
            {
                (stamp.skill, stamp.control)
                for in_file in stamps.values()
                for stamp in in_file
                if stamp.skill not in known
            }
        )
    )
    # The skill version each skill was last deployed at, for the one comparison
    # a declination admits: whether the repository has already moved past the
    # release it declines.
    deployed_versions = {
        stamp.skill: stamp.skill_version for in_file in stamps.values() for stamp in in_file
    }
    inventory = installed if installed is not None else read_inventory()
    problems = decision_problems(
        declined, deployed_versions, today or datetime.date.today(), inventory
    )
    return Report(
        plugin=plugin,
        gates=tuple(reports),
        foreign=foreign,
        declined=declined,
        stale_decisions=tuple(problems),
        unreconciled=tuple(unreconciled(declined, inventory)),
        unmanaged_pins=unmanaged,
    )


_RUNG_ORDER = {"blocking": 0, "blocking (baselined)": 1, "warn": 2, "advisory": 3}
_STATE_ORDER = {
    State.AHEAD: 0,
    State.NOT_APPLICABLE: 5,
    State.NEVER_DEPLOYED: 1,
    State.STALE: 2,
    State.UNRECORDED: 3,
    State.CURRENT: 4,
}


def _loudness(report: GateReport, register: Register) -> tuple[int, int, int, str]:
    """Order comes from the register: the tier and rung of what the gate carries.

    `02-skill-family.md` § Loudness: a Tier-1 security control awaiting
    deployment reads differently from a markdown rule, and the register already
    says so — inventing a severity field here would be a second copy of what
    `tier` and `rung` mean.
    """
    controls = [
        c for c in register.controls if isinstance(c, Control) and c.id in report.gate.controls
    ]
    tier = min((c.tier for c in controls), default=9)
    rung = min((_RUNG_ORDER.get(c.rung, 9) for c in controls), default=9)
    return (_STATE_ORDER[report.state], tier, rung, report.gate.name)


def render(report: Report, register: Register) -> str:
    lines = [
        f"deployment report — plugin {report.plugin}, "
        f"register v{register.version} (contract {register.register_contract})",
        "",
    ]
    for gate in sorted(report.gates, key=lambda g: _loudness(g, register)):
        lines.append(
            f"  {gate.gate.name:<20} {gate.state!s:<15} "
            f"contract {gate.gate.contract}   {', '.join(gate.gate.controls)}"
        )
        lines.append(f"           {_explain(gate)}")
        if gate.absent_paths:
            lines.append(f"           artefacts absent: {', '.join(gate.absent_paths)}")
    if report.foreign:
        lines.append("")
        lines.append("  Deployed by a skill this plugin does not ship:")
        lines.extend(f"    {skill:<20} {control}" for skill, control in report.foreign)
    if report.declined:
        lines.append("")
        lines.append("  Deliberately not deployed:")
        for entry in report.declined:
            where = f" ({entry.adr})" if entry.adr else ""
            lines.append(
                f"    {entry.skill}@{entry.version:<10} DECLINED until "
                f"{entry.review_by}{where}"
            )
            lines.append(f"        {entry.reason}")
        lines.append(
            "    A declination covers the version it names and no later one: a "
            "new release re-opens the question."
        )
        if report.unreconciled:
            lines.append(
                "    Not reconciled against an installed release (reported, not assumed "
                "current):"
            )
            lines.extend(f"      ? {note}" for note in report.unreconciled)
    if report.stale_decisions:
        lines.append("")
        lines.append("  The record itself has stopped describing reality:")
        lines.extend(f"    ✗ {problem}" for problem in report.stale_decisions)
    if report.unmanaged_pins:
        lines.append("")
        lines.append("  Pinned, and no bot will ever propose moving it:")
        lines.extend(f"    ! {finding}" for finding in report.unmanaged_pins)
        lines.append(
            "    An unmanaged pin does not drift — it never moves, and the "
            "supply-chain controls stay green over it. Reported, not enforced."
        )
    owed, defective = report.owed, report.defective
    lines += [
        "",
        f"Summary: {len(report.gates) - len(owed) - len(defective)} current or "
        f"not applicable, {len(owed)} owed a deployment, {len(defective)} defective, "
        f"{len(report.declined)} declined",
    ]
    if owed:
        lines.append(
            "Staleness is reported, never enforced — a gate above is a "
            "recommendation to re-run it, not a failure."
        )
    return "\n".join(lines)


def render_json(report: Report, register: Register) -> str:
    """The report `render` prints, as data (ADR 0056), deciding nothing of its own."""
    document = {
        "format": JSON_FORMAT,
        "checker_version": installed_version("register-check"),
        "register_version": register.version,
        "register_contract": register.register_contract,
        "plugin": str(report.plugin),
        "gates": [
            {
                "gate": gate.gate.name,
                "state": str(gate.state),
                "contract": gate.gate.contract,
                "controls": list(gate.gate.controls),
                "deployed": list(gate.deployed),
                "stamped_paths": list(gate.stamped_paths),
                "absent_paths": list(gate.absent_paths),
                "explanation": _explain(gate),
            }
            for gate in sorted(report.gates, key=lambda g: _loudness(g, register))
        ],
        "owed": [gate.gate.name for gate in report.owed],
        "defective": [gate.gate.name for gate in report.defective],
        "foreign": [{"skill": skill, "control": control} for skill, control in report.foreign],
        "declined": [
            {
                "skill": entry.skill,
                "version": entry.version,
                "reason": entry.reason,
                "review_by": entry.review_by.isoformat(),
                "adr": entry.adr,
            }
            for entry in report.declined
        ],
        "stale_decisions": list(report.stale_decisions),
        "unreconciled": list(report.unreconciled),
        "unmanaged_pins": list(report.unmanaged_pins),
    }
    return json.dumps(document, indent=2)


def _explain(gate: GateReport) -> str:
    match gate.state:
        case State.NOT_APPLICABLE:
            return "no control this gate carries applies to this repository"
        case State.NEVER_DEPLOYED:
            return "no stamp names this gate — run it to deploy its controls"
        case State.UNRECORDED:
            return (
                "deployed before the stamp recorded a gate contract (ADR 0038) — "
                "whether it is current is unknown until it next deploys"
            )
        case State.STALE:
            return (
                f"deployed at contract {', '.join(str(c) for c in gate.behind)} — "
                "what this gate writes has changed since"
            )
        case State.CURRENT:
            return f"stamped at contract {gate.gate.contract} in {len(gate.stamped_paths)} file(s)"
        case State.AHEAD:
            ahead = sorted({c for c in gate.deployed if c is not None and c > gate.gate.contract})
            return (
                f"a stamp claims contract {', '.join(str(c) for c in ahead)}, which the "
                "installed gate has not reached — a defect, not staleness"
            )
    raise AssertionError(f"unhandled state {gate.state!r}")
