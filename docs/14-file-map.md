# Where everything is

The map for someone who knows what they need and not where it lives. Every
other document here explains a *decision*; this one only answers *which file*.

**It is checked, not maintained by hope.** `tests/test_file_map.py` fails the
build if this file names a path that does not exist, and — for the repository
root and its top-level directories — if a tracked entry exists that this file
does not name. The second half is the one that matters: a map is an allow-list,
and what an allow-list leaves out is invisible
([ADR 0019](adr/0019-exemptions-cannot-hide-tracked-files.md) is the same
argument about exemptions). Below the top level the check is existence only, so
a new file inside `src/` does not fail a build over documentation.

## The three files people look for first

| File | What it is | Do not confuse it with |
| --- | --- | --- |
| `controls.yaml` | **The register.** A control entry *is* the control, not documentation of one. Everything else derives from it | Anything below. If a rule could reasonably differ between Equal Experts repositories, it belongs here |
| `deployment-decisions.yaml` | What this repository has deliberately **not** deployed, and why, and until when. Read by `register-check deployments` | The register. This is *posture* — it must never reach `controls.yaml` or `plugins/` ([ADR 0022](adr/0022-a-platform-token-ci-carries.md) requirement 6) |
| `.claude/skill-config.yaml` | What a third-party skill writes here, keyed by skill name ([ADR 0042](adr/0042-a-deploying-skill-reads-local-configuration.md)). Real from `lint-md` 1.0.8, which reads it at pre-flight; it holds this repository's `invocation` and its empty `ignores` | The two above. It is read by a **skill**, at deploy time, and its format belongs to `ee-skills` rather than to us — nothing stamps it and no control reads it |

Those three are separate on purpose, and the sharpest reason is that two of them
fail in opposite directions: a malformed `deployment-decisions.yaml` **exits 2**,
because reading it as empty would report every declined deployment as a chore
nobody got to; a malformed `.claude/skill-config.yaml` falls back to defaults and
**continues**, because a broken preference file should not stop a deployment.
One file cannot hold both policies.

## The repository root

| Path | What it is |
| --- | --- |
| `controls.yaml` | The register — see above |
| `controls.published.yaml` | **Generated.** The register an adopter fetches, derived from `controls.yaml` by removing `# local-only` entries ([ADR 0048](adr/0048-the-published-register-is-derived.md)). Written by `register-check publish`; `tests/test_published_register.py` fails a stale one |
| `deployment-decisions.yaml` | Declined deployments — see above |
| `START-HERE.md` | **The adoption quickstart.** The happy path for a junior with a Mac and nothing else: what to install, which credentials, six steps. Held runnable by `tests/test_start_here.py` |
| `adopt.sh` | **The bootstrap.** The one file an adopter fetches by hand, before Claude Code or a plugin exists — it needs `git` and `curl` and no credentials, resolves the newest tag, clones it anonymously, and runs the route in `plugins/control-register/templates/adopt/` from there ([ADR 0049](adr/0049-the-adoption-route-is-executable.md) revision 2). Fetched from `main` and pins nothing by design: it holds no rules, and what it clones is pinned |
| `HOW-IT-WORKS.md` | The mechanism in one screen, for a person deciding whether to adopt or reading a verdict. Links `docs/00-concepts.md` for every term rather than restating one |
| `README.md` | What this repository is, for a person arriving cold |
| `CLAUDE.md` | The same ground for an agent, plus every decision in force |
| `LICENSE` | Held byte-identical with each plugin's own copy — `plugins/control-register/LICENSE` and `plugins/craft/LICENSE`, since a plugin is copied without the repository root |
| `pyproject.toml` | The single definition of ruff, mypy and pytest that every locus reads, plus the package's support floor |
| `uv.lock` | The Python pin. `package-lock.json` is the node one |
| `package.json`, `package-lock.json` | `markdownlint-cli2`, and the path every locus invokes it by |
| `.python-version` | The interpreter the gates run on ([ADR 0027](adr/0027-the-interpreter-is-a-pinned-tool.md)). A *pin*, not the support floor |
| `.markdownlint.yaml` | DOC-001's rule set |
| `.markdownlint-cli2.yaml` | DOC-001's runner config — `gitignore: true`, `ignores: []` |
| `.pre-commit-config.yaml` | Both local loci. A hook's `stages:` says which ([ADR 0039](adr/0039-a-push-is-a-locus.md)) |
| `.gitignore` | Two of its lines are a stamped SEC-001 artefact |
| `renovate.json` | Update proposals for what Dependabot cannot see |

## The directories

| Path | What is in it |
| --- | --- |
| `craft/` | **The Craft register**, one file per scope: `craft/meta.yaml` holds the contract, levels, sources and profile versions, and `craft/python.yaml`, `craft/react.yaml` and `craft/any.yaml` the properties for each scope. Coding standards, *not* controls: a craft rule crosses into `controls.yaml` only by [ADR 0051](adr/0051-a-craft-rule-becomes-a-control-by-being-installed.md)'s route. Checked by `tests/test_craft_register.py`, deliberately **not** by `register-check` ([ADR 0053](adr/0053-the-craft-mapping-is-register-data.md)) |
| `docs/` | Every explanation. `docs/00-concepts.md` first, then the numbered files; `docs/adr/` holds the decisions |
| `docs/craft/` | The Craft workstream's **records** — its plan, naming standard and one file per stage, set out in `docs/craft/plan.md`; deliberately not numbered into the files above, and not a phase of the build plan. `docs/craft/assess.rules.md` is a stage record and **not a source**: the register above replaced it ([ADR 0053](adr/0053-the-craft-mapping-is-register-data.md)), and a test holds the two together |
| `src/` | `src/register_check/` — the checker. One assert implementation, read by every locus. `--format json` prints `run` and `deployments` as data for a consumer elsewhere, from the same results as the text report ([ADR 0056](adr/0056-the-checker-has-a-machine-readable-report.md)) |
| `tests/` | The suite. Several tests hold rules that govern *this* repository rather than a conformant one |
| `plugins/` | Two plugins, because they answer two questions. `plugins/control-register/` — what an adopter installs to be *conformant*: nine skills, the templates they write from, and the shared prose. `plugins/craft/` — what they install to have *coding standards*: `craft-install`, and `plugins/craft/profiles/`, which is the Craft register **rendered** into the configuration that skill copies. The rendering is written by `scripts/craft_publish.py` and held to the register by `tests/test_craft_plugin.py`, so the published copy cannot drift from `craft/` |
| `scripts/` | `scripts/plan_progress.py`, the derived view of the build plan's exit criteria; Craft's three S5 scripts — `scripts/craft_select.py` (what a profile turns on and what each rule costs, resolved from the register), `scripts/craft_render.py` (the configuration and the unenforced residue, rendered from it) and `scripts/craft_publish.py` (that rendering, written into `plugins/craft/`); and Craft's four S3 scripts — `scripts/craft_scaffold.py` (the subject: a new repository of each stack), `scripts/craft_profile.py` (the instrument: the configuration, at either level), `scripts/craft_cases.py` (the witnesses, violations and probes) and `scripts/craft_cost.py` (what each selected rule costs, and which rules a plugin's `recommended` would not give you). The first three materialise into, and the fourth reads, the gitignored working directory this repository also clones sources into — they cannot be tracked, and `docs/craft/review.bench.md` § What the criteria are measured on says why |
| `.github/` | `.github/workflows/` (four), `.github/dependabot.yml`, and `.github/rulesets/default-branch.json` — the record of what the platform is asked to enforce |
| `.devcontainer/` | The container this repository is developed in. `.devcontainer/setup.sh` installs the tools; `.devcontainer/check-auth.sh` reports what is missing |
| `.claude/` | `.claude/hooks/md-lint.py`, `.claude/settings.json`, and `.claude/skills/` — tracked symlinks into the plugin ([ADR 0033](adr/0033-the-submission-tool-reaches-the-skills-by-symlink.md)) |
| `.claude-plugin/` | `.claude-plugin/marketplace.json` — this repository as a marketplace |
| `.vscode/` | `.vscode/settings.json` — which extension holds a gated file type ([ADR 0029](adr/0029-the-editor-locus-is-configured-by-the-repository.md)) |

## The four workflows, and which one gates

Only one of them decides whether a change can merge.

| Workflow | Runs on | Gates a merge? |
| --- | --- | --- |
| `.github/workflows/register-check.yml` | push, pull_request, schedule | **Yes** — its job id is the status check CI-001 requires |
| `.github/workflows/lint.yml` | push, pull_request | No |
| `.github/workflows/support-floor.yml` | push, pull_request | **No, deliberately** — a support claim failing is a thing to know, not a reason a conformant change cannot merge |
| `.github/workflows/conformance-sweep.yml` | schedule, workflow_dispatch | **No** — it reports and never fixes, and does not fail on findings |

Neither of the last two may enter CI-001's
`required_checks:`.

## Inside the plugin

`plugins/control-register/` is what an adopter installs, and nothing in it may
carry a value the register pins or a fact about this repository's own posture.

| Path | What is in it |
| --- | --- |
| `plugins/control-register/skills/gate-*/` | Six gates. Each deploys the controls that name it in `deployed_by` |
| `plugins/control-register/skills/register-adopt/` | The front door. Dispatches the others and writes nothing itself |
| `plugins/control-register/skills/register-install/` | Puts the checker where the loci can reach it. Writes no provenance stamp — a stamp names a control, and there is none to name |
| `plugins/control-register/skills/register-variance/` | Reports which way a config change moved ([ADR 0040](adr/0040-a-declined-classification-is-a-verdict.md)) |
| `plugins/control-register/reference/` | Prose more than one skill must follow, shipped once ([ADR 0036](adr/0036-shared-skill-prose-has-one-home.md)) |
| `plugins/control-register/templates/devcontainer/` | The devcontainer an adopter copies |
| `plugins/control-register/templates/sweep/` | The scheduled sweep an adopter copies |
| `plugins/control-register/.claude-plugin/deploys.json` | One deployment contract **per gate**, not per plugin |
