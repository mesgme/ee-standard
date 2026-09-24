# CLAUDE.md

Guidance for Claude Code in this repository.

**What this repo is.** A control register for Equal Experts repositories:
`controls.yaml` defines what "conformant" means, a family of Claude skills
deploys the gates, and `register-check` (`src/register_check/`) audits them.
[`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) is the mechanism in one screen;
[`docs/14-file-map.md`](docs/14-file-map.md) answers *which file*.

**Every phase is complete.** `uv run python scripts/plan_progress.py` is the
derived view and `docs/04-build-plan.md` is the only list of outstanding work.
Never keep a second copy of that status here.

**Do not treat a ticked box as settled.** Eight have been re-opened after being
ticked. `docs/09-phase-1.5-review.md` § A–§ H records what each assert was wrong
about; read it before touching `src/register_check/`. **`§ A`–`§ H` anywhere in
this repo refers to that file.**

## Commands

- Full conformance run: `uv run register-check` (also: `schema`, `run --tier 1`,
  `meta GOV-001`, `assert <name>`, `explain <ID>`). CI runs it in
  `.github/workflows/register-check.yml`.
- Which gates are deployed and current: `uv run register-check deployments`. It
  is **not** part of a conformance run and never fails a build over staleness —
  exit `0` over any number of stale gates, non-zero only for a stamp ahead of
  the installed gate, or for a **record** that has stopped describing reality.
  Every gate here reads `UNRECORDED` until it is re-run, which is ADR 0038
  reporting itself rather than a defect. From ADR 0043 it also reconciles each
  declination against the **installed** skill, so its verdict depends on the
  machine: this container has a plugin inventory and CI has none, and a run that
  cannot look says so rather than reporting agreement.
- Quality gates: `uv run ruff check .`, `uv run mypy`, `uv run pytest` — all
  configured in `pyproject.toml`, the single definition every locus reads.
- Build-plan progress: `uv run python scripts/plan_progress.py` — a derived view
  of the exit criteria in `docs/04-build-plan.md`, which stays the single source.
  It stores nothing and infers no gating; it exits non-zero if a criterion is
  marked re-opened while still ticked. Never maintain a second list of this work.
- Lint markdown: `node_modules/.bin/markdownlint-cli2 "**/*.md"` — also runs via
  a PostToolUse auto-fix hook on every file you write, a pre-commit hook, and
  `.github/workflows/lint.yml`. **The path is the command.** There is no
  `markdownlint-cli2` on `PATH` in this container, and a bare one falls through
  to `npx`, which downloads a version rather than using the one
  `package-lock.json` pins — ADR 0020 case C, in this file's own instructions.
  `.pre-commit-config.yaml` and `.github/workflows/lint.yml` both spell the path.
- Run all pre-commit hooks: `uv run pre-commit run --all-files`
- **Before you push**, most of what CI runs now runs itself. Register contract
  31 added a `pre-push` locus ([ADR 0039](docs/adr/0039-a-push-is-a-locus.md)),
  and `git push` runs `uv run pytest` (TST-001) and
  `register-check run --control SUP-001 --control SUP-002` — provided
  `.git/hooks/pre-push` is installed, which `setup.sh` does and `check-auth.sh`
  reports. Two commands are still yours to remember, and neither can be wired:

  ```bash
  uv run register-check   # the whole register; the hooks run five controls
  uv sync --frozen        # SUP-001 — the lockfile is current
  ```

  The first exits `3` locally and that is expected rather than a failure —
  SEC-003's remote blocks answer only inside a GitHub Actions job — which is
  exactly why a hook cannot run it: a hook that tolerated `3` would accept a run
  that verified nothing. The second would verify the wrong thing at that locus,
  because every `uv run` above it re-locks on disk before `--frozen` is reached.
  **Never wrap these in a script under `scripts/`** — that is a second copy of
  the CI definition, free to drift from the workflow it mirrors.
- Verify container auth/tools: `.devcontainer/check-auth.sh`
- `gh` for repos in the Eaiger-Ent org (ambient `GITHUB_TOKEN`); `gh-ee-skills`
  for repos in the EqualExperts org (ee-skills, ee-skills-incubator) — the
  wrapper scopes `EE_SKILLS_GITHUB_TOKEN` to a single invocation.

All development happens inside the devcontainer (`docs/06-devcontainer-setup.md`
is the operator guide). Host secrets arrive via `.devcontainer/fetch-secrets.sh`
(macOS Keychain → `.devcontainer/.env`, from which `.devcontainer/.env.docker`
is derived for `--env-file`; both are gitignored and must stay so — SEC-001
depends on those lines).

## The core invariant

A register entry in `controls.yaml` **is** the control, not documentation of
one. Every other artefact — CI workflow, pre-commit config, gate skill,
devcontainer, checker — derives from the register rather than restating it.
Never introduce a second copy of a rule (in prose, CI, or config) that could
drift from the register; that duplication ("theme T-2") is the failure this repo
exists to prevent.

**Python counts as a second copy.** Per
[ADR 0018](docs/adr/0018-register-checker-boundary.md) (**Accepted** 2026-08-17,
**implemented** over contracts 3, 5, 6 and 8), before writing a rule into
`src/register_check/` ask: *could a reasonable Equal Experts repository need this
to differ without changing the checker?* If yes, it belongs in `controls.yaml` —
mandated tool names and their per-locus evidence live in `stacks:` — including which files a stack's gates must cover and where each
tool's allow-list lives — lockfile
ecosystems, test-command spellings and frozen-install idioms in `ecosystems:`,
tool versions **and the loci that repeat them** in `tools:`,
failure-suppression idioms in `suppression:`, the credential names SEC-002
forbids in `cloud_credentials:`, and anything specific to
one control in its verify block's `args:`. If no, the checker may hold it, but
the reason must be recorded in ADR 0018 — the predicate grammar, the ID pattern, semver
strictness, `rationale_adr` existence and the Tier-1 baseline rule are
properties of the register format, not of any repository. An unreasoned rule in
the checker is the failure, not an exception to it.

## The gotchas that cost the most

Each of these has been paid for once. None is derivable from the code.

- **Work in the container, not on the host.** Only four steps are the host's:
  `claude setup-token` and the Keychain entries, `fetch-secrets.sh` (it **is**
  `initializeCommand`), `devcontainer build`/`up`, and copying a template in
  before a container exists. A host run once reported green about a uv version
  it was not using. `docs/08-adopting.md` § 2.0a is the split.
- **A wired locus is not an installed hook.** `.pre-commit-config.yaml` states
  intent; `.git/hooks/pre-commit` is whether anything runs, and every gate reads
  the first. It cannot become a control — `.git/hooks/` is untracked and CI has
  none.
- **A support floor is not a pin.** `.python-version` selects (3.14);
  `requires-python` constrains. `[tool.ruff] target-version` is deliberately
  absent — ruff derives it, and writing it out was a third copy that drifted.
- **A shebang resolves from `PATH`.** Every tracked script reads
  `#!/usr/bin/env -S uv run python`; `tests/test_toolchain_pin.py` fails one
  that does not. The base image still ships a `python3` below the floor.
- **This repository is public.** Write nothing that assumes privacy.
- **Do not invoke a gate casually.** All eight skills are model-invocable here
  and they write into this repository.
- **Never fill in a provenance stamp by hand**, and never refresh one with no
  run behind it. A stamp behind the register is staleness and is never enforced;
  a stamp ahead of it is a defect and fails.
- **Exit `3` is not a failure.** No violation found, something unverified.
  `uv run register-check` exits `3` locally, permanently, because SEC-003's
  remote blocks answer only inside an Actions job.

## Rules for editing `controls.yaml`

- Bump `meta.register_contract` when a control's `rung`, `verify`, `variance` or
  `applies_to` changes, or when the register gains a field a skill reading it
  must understand — skills read it to detect stale deployments.
- Every control must cite an external, resolving standard URL; verify URLs
  before committing them.
- An unknown `assert` name is a schema error, not a skipped check (Phase 1 exit
  criterion — keep the closed set in sync with the checker when it exists).
- Meta-controls (GOV-001/002/003) check the register itself, not the code.

## Documents

Read `docs/00-concepts.md` first for the vocabulary, then `docs/14-file-map.md`
for where anything lives. Both are more current than any list kept here.

| Document | For |
| --- | --- |
| `HOW-IT-WORKS.md` | The mechanism, one screen |
| `START-HERE.md` | Adopting the standard, six steps |
| `docs/00-concepts.md` | The vocabulary every other document assumes |
| `docs/01-register-schema.md` | Field-by-field spec of `controls.yaml` |
| `docs/04-build-plan.md` | The only list of outstanding work |
| `docs/08-adopting.md` | The adoption reference. Every phase owes it the steps it introduces |
| `docs/14-file-map.md` | Which file, and why three config files are three |
| `docs/adr/` | Every decision in force, **except any marked `Proposed`** — open, awaiting a second reader, and not to be implemented as though settled. Today: 0056 (`--format json`). `archive/` holds the retired |
| `docs/09`–`docs/17` | Phase records and reviews, in order |
| `docs/craft/plan.md` | **Craft** — the coding-standards workstream for Python and React, which the register is deliberately silent about. Its own naming standard and stages; not a phase of the build plan, and it mints no controls |
| `craft/` | **The Craft register** — `meta.yaml` plus one file per scope. Coding standards, not controls. `tests/test_craft_register.py` checks it; `register-check` deliberately does not (ADR 0053), and `docs/craft/assess.rules.md` is now a stage record rather than a source |
| `plugins/craft/` | **What an adopter installs** — `craft-install`, and `profiles/`, which is the register above *rendered* into the configuration that skill copies. Written by `uv run python scripts/craft_publish.py`, held to the register by `tests/test_craft_plugin.py`. Change `craft/` and the build fails until you re-publish |

## Decisions in force

Every ADR in `docs/adr/` is Accepted and binding, except any the row above marks
`Proposed`. **Read the ADR rather than a summary** — a restatement here is a
second copy, which is the failure this repository exists to prevent, and this
file has already carried a drifted one.

The ones most likely to catch you out, by what they govern:

| If you are touching | Read |
| --- | --- |
| A control's verdict or exit code | ADRs 0016, 0017 |
| `kind: remote`, tokens, CI credentials | ADRs 0021, 0022 |
| The register/checker boundary — before adding a rule to Python | **ADR 0018** |
| The devcontainer, uv, or the interpreter | ADRs 0027, 0028, 0030, 0034, 0037 |
| The editor locus | ADR 0029 |
| A gate skill, or shared skill prose | ADRs 0033, 0035, 0036, 0038 |
| `pinned_at`, or a gate writing the register | **ADR 0045** |
| Loci, pins, digests, or a bot's config | ADRs 0020, 0039, 0041 |
| Writing or amending an ADR | ADRs 0024, 0025, 0026 |
| The adopter's route, or the marketplace | ADRs 0032, 0042, 0043, 0044 |
| Anything in the Craft workstream | **ADRs 0051, 0052, 0053, 0054, 0055** |

**Naming (ADR 0031).** The plugin is `control-register`, the checker is
`register-check`, the non-gate skills are `register-*`. The gates keep their
names. The **repository** is not renamed: `ee-standard` in a path, URL or secret
prefix means the repository. Outside `docs/adr/`,
`grep -rn 'standard[-_]check'` returning nothing is the finish condition.

**Enforcement is never Claude.** Gates are pinned binaries reading pinned
configs. A skill may install or explain a gate; it cannot be one.

**Model selection** is ADR 0023's: three classes, a floor per class, and
`CLAUDE_CODE_SUBAGENT_MODEL` forbidden. Do not restate the floors here —
`.claude/agents/*.md` frontmatter is the only copy the harness reads.

## One thing this repository does not do

`docs/04-build-plan.md` § The one place this repository does not do what it asks
of everyone else records a posture divergence, and `tests/test_posture.py` fails
the build if that record is deleted, or if the posture reaches `controls.yaml`
or anything under `plugins/`. An undocumented divergence is indistinguishable
from an oversight.
