"""Report rendering, ordered by tier then rung."""

from __future__ import annotations

import json
from collections import Counter
from importlib.metadata import version
from typing import Any

from register_check.register import Control, Partial, Register
from register_check.runner import ControlResult, Verdict

_RUNG_ORDER = {"blocking": 0, "blocking (baselined)": 1, "warn": 2, "advisory": 3}

_MARK = {
    Verdict.PASS: "✓",
    Verdict.FAIL: "✗",
    Verdict.SKIPPED_PREDICATE: "-",
    Verdict.SKIPPED_NO_CREDENTIALS: "-",
    Verdict.UNCLASSIFIED: "?",
    # Distinct from `?` on purpose: unreadable is *we could not tell*, and
    # this is *we know, and the plan does not sell it* (ADR 0047).
    Verdict.UNAVAILABLE_PLAN: "⊘",
}


def _sort_key(result: ControlResult) -> tuple[int, int, str]:
    control = result.control
    assert isinstance(control, Control)
    return (control.tier, _RUNG_ORDER.get(control.rung, 9), control.id)


def _summary(
    results: list[ControlResult], meta_results: list[tuple[str, str, Verdict, str]]
) -> dict[str, int]:
    """The counts both renderers print, computed once so they cannot disagree."""
    counts = Counter(result.verdict for result in results)
    return {
        "passed": counts[Verdict.PASS],
        "failed": counts[Verdict.FAIL],
        "skipped_predicate": counts[Verdict.SKIPPED_PREDICATE],
        "skipped_no_credentials": counts[Verdict.SKIPPED_NO_CREDENTIALS],
        "unclassified": counts[Verdict.UNCLASSIFIED],
        "unavailable_plan": counts[Verdict.UNAVAILABLE_PLAN],
        "meta_passed": sum(1 for meta in meta_results if meta[2] is Verdict.PASS),
        "meta_total": len(meta_results),
    }


def render(
    register: Register,
    results: list[ControlResult],
    meta_results: list[tuple[str, str, Verdict, str]],
) -> str:
    lines = [
        f"control register conformance report — register v{register.version} "
        f"(contract {register.register_contract})",
        "",
    ]
    tier: int | None = None
    for result in sorted(results, key=_sort_key):
        control = result.control
        assert isinstance(control, Control)
        if control.tier != tier:
            tier = control.tier
            lines.append(f"Tier {tier}")
        lines.append(f"  {control.id:<8} {result.verdict!s:<25} {control.title}")
        if result.verdict is Verdict.SKIPPED_PREDICATE:
            lines.append(f"           - {result.note}")
        elif result.verdict is not Verdict.PASS:
            lines.extend(
                f"           {_MARK[block.verdict]} {block.block.describe()} — {block.message}"
                for block in result.blocks
            )
        # ADR 0017: a verdict that does not cover everything the control claims
        # says so, whatever the verdict was. Printed even for PASS — especially
        # for PASS, since that is the verdict a partial block would otherwise
        # let overstate its evidence.
        lines.extend(
            f"           partial: {block.block.partial.unverified} "
            f"(expires {block.block.partial.expires.isoformat()})"
            for block in result.blocks
            if block.block.partial is not None
        )
    # A narrowed run (`--control`) audits one deployment, not the register, so
    # it carries no meta-controls. Printing an empty heading over nothing would
    # read as three meta-controls that passed silently.
    if meta_results:
        lines.append("Meta")
    meta_by_id = {meta.id: meta for meta in register.meta_controls}
    for meta_id, title, verdict, message in meta_results:
        lines.append(f"  {meta_id:<8} {verdict!s:<25} {title}")
        if verdict is not Verdict.PASS:
            lines.append(f"           {_MARK[verdict]} {message}")
        lines.extend(
            f"           partial: {block.partial.unverified} "
            f"(expires {block.partial.expires.isoformat()})"
            for block in meta_by_id[meta_id].verify
            if block.partial is not None
        )
    # Counts stay control-only so "N passed" keeps meaning what it always has;
    # meta-controls have their own line. The notes below read both, because a
    # meta-control that could not be verified makes the report incomplete too.
    summary = _summary(results, meta_results)
    all_verdicts = [result.verdict for result in results] + [meta[2] for meta in meta_results]
    lines += [
        "",
        "Summary: "
        f"{summary['passed']} passed, "
        f"{summary['failed']} failed, "
        f"{summary['skipped_predicate']} skipped (predicate), "
        f"{summary['skipped_no_credentials']} skipped (no credentials), "
        f"{summary['unclassified']} unclassified, "
        # Printed even when zero, unlike a footnote. A repository running
        # with a recorded plan limit should see it in the same line it
        # reads for everything else (ADR 0047 rule 5).
        f"{summary['unavailable_plan']} unavailable (plan); "
        f"meta-controls: {summary['meta_passed']}/{summary['meta_total']} passed",
    ]
    # Two different reasons a run gathered no evidence, reported separately
    # because they are fixed differently: one needs credentials, the other needs
    # the tool installed. Neither is a claim that the control holds (ADR 0016).
    if Verdict.SKIPPED_NO_CREDENTIALS in all_verdicts:
        lines.append(
            "Note: remote checks were skipped without credentials — this report is "
            "incomplete, not a claim that those controls hold."
        )
    if Verdict.UNCLASSIFIED in all_verdicts:
        lines.append(
            "Note: some controls could not be verified — this report is incomplete, "
            "not a claim that those controls hold."
        )
    return "\n".join(lines)


#: The shape `render_json` emits (ADR 0056). Adding a field leaves it alone;
#: renaming or removing one bumps it, because a consumer keeping history reads
#: documents written by every checker release it has ever run.
JSON_FORMAT = 1


def _partial(partial: Partial | None) -> dict[str, str] | None:
    if partial is None:
        return None
    return {"unverified": partial.unverified, "expires": partial.expires.isoformat()}


def render_json(
    register: Register,
    results: list[ControlResult],
    meta_results: list[tuple[str, str, Verdict, str]],
) -> str:
    """The report `render` prints, as data (ADR 0056).

    Built from the same results and the same `_summary`, and deciding nothing
    of its own: a second renderer that computed a verdict would be a second
    report, free to disagree with the first.
    """
    controls: list[dict[str, Any]] = []
    for result in sorted(results, key=_sort_key):
        control = result.control
        assert isinstance(control, Control)
        controls.append(
            {
                "id": control.id,
                "title": control.title,
                "tier": control.tier,
                "rung": control.rung,
                "verdict": str(result.verdict),
                "note": result.note,
                "blocks": [
                    {
                        "describe": block.block.describe(),
                        "verdict": str(block.verdict),
                        "message": block.message,
                        "partial": _partial(block.block.partial),
                    }
                    for block in result.blocks
                ],
            }
        )
    meta_by_id = {meta.id: meta for meta in register.meta_controls}
    document = {
        "format": JSON_FORMAT,
        "checker_version": version("register-check"),
        "register_version": register.version,
        "register_contract": register.register_contract,
        "controls": controls,
        "meta": [
            {
                "id": meta_id,
                "title": title,
                "verdict": str(verdict),
                "message": message,
                "partial": [
                    _partial(block.partial)
                    for block in meta_by_id[meta_id].verify
                    if block.partial is not None
                ],
            }
            for meta_id, title, verdict, message in meta_results
        ],
        "summary": _summary(results, meta_results),
    }
    return json.dumps(document, indent=2)
