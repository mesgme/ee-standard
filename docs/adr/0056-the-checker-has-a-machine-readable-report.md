# ADR 0056: The Checker Has a Machine-Readable Report

**Status:** Proposed
**Date:** 2026-09-24
**Revision:** 1

## Background

**The problem.** `register-check` prints its verdicts for a person to read, and
then they are gone. Nothing records *when* a control started failing, and
nothing sees more than one repository at a time: `conformance-sweep.yml` keeps
the current state of one issue in one repository. A consumer outside this
repository — a fleet sweep keeping verdict history across adopters — needs the
report as data.

**Parsing the text report is the obvious route and the wrong one.** Its layout
is written for a reader: column widths, a `Tier N` heading, indented block lines
whose marks mean different things. Every change to how it reads would break a
parser nobody here can see, and the parser would be the consumer's private copy
of the report's grammar — a second copy, outside this repository, of a thing
this repository changes freely.

## Alternatives Considered

### Option 1: Consumers parse the text report

**Rejected.** It makes the text layout a contract without anybody deciding so,
and it fails silently: a reworded summary line parses as zero of something.

### Option 2: A separate `register-check export` command

A command that runs the audit and writes JSON.

**Rejected.** A second command is a second entry point that has to select,
narrow and exit exactly as `run` does. `run --control` exists precisely so that
a gate and the auditor cannot take different paths (Phase 2); an export command
would reopen that.

### Option 3: A `--format` option on the commands that already report

**Chosen.** `run` (and the bare command) and `deployments` print the same report
as JSON under `--format json`. Nothing about which controls run, or how, changes.

## Decision

**`--format json` renders the same results the text report renders, and decides
nothing of its own.**

1. **Same verdicts.** The JSON renderer is built from the same `ControlResult`s
   and the same summary counts as the text one (`report._summary`), so the two
   cannot disagree. It computes no verdict.
2. **Same exit code.** ADR 0016's codes belong to the verdicts, not to how they
   are printed. `3` stays `3` in JSON.
3. **Text stays the default.** Every locus that runs the checker today reads
   text and is untouched.
4. **A command that cannot honour the format says so** and exits `2`, rather
   than falling back to text a parser would choke on.
5. **`format` is a contract.** Each document carries `"format": 1`. Adding a
   field leaves it alone; renaming or removing one bumps it. A consumer keeping
   history reads documents from every checker release it has ever run, and needs
   to know which shape it is reading.
6. **Each document says what produced it:** `checker_version`,
   `register_version` and `register_contract`. A verdict kept for later is
   evidence only alongside what decided it.

## Consequences

**The JSON shape is now something this repository can break.** The text report
can still change freely; the JSON cannot change without a `format` bump.
`tests/test_report_json.py` holds it to the text report of the same run, which
catches a renderer deciding something the text one does not — it does not catch
a field being renamed, which is what the `format` rule is for.

**Nothing in this repository consumes it.** It exists for a consumer elsewhere.
That is deliberate: history across repositories is not the checker's job, and a
checker that kept it would be a state store inside a tool whose every verdict is
recomputed from the files.

**It reaches adopters only through a release.** An adopter's pinned
`tools.register-check.install.ref` decides whether its checker has the option;
a consumer running an older pin gets exit `2` and must say so rather than guess.

## Related ADRs

- [ADR 0016](0016-exit-codes-for-unverifiable-controls.md) — the exit codes
  this leaves untouched.
- [ADR 0018](0018-register-checker-boundary.md) — the output format is a
  property of the checker, not of any repository, so it belongs in code.
