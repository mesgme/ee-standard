# Adopting the standard

For someone who did not author this repository and wants their own repository to
satisfy it. Start here; the other documents are specifications, and you should
not have to read a specification to get started.

**What this covers that nothing else does: the steps no tool can take for you.**
Most of conformance is machinery — a checker, a devcontainer, a family of gate
skills. But several Tier-1 controls rest on *account and platform state*: who
owns the repository, whether a bot is installed, whether a branch is protected.
No skill can install a GitHub App on your organisation. Those steps are the ones
that get discovered late and cost the most, so they come first here.

## Status — what exists today

Read this table before following anything below it. A guide that describes
tooling which does not exist is the failure this repository was written to
prevent, so the gaps are stated rather than glossed.

| Part | State | Where it is |
| --- | --- | --- |
| The `control-register` plugin — everything below arrives in it | **Exists**; install it first | `claude plugin install control-register@ee-standard`, and § 0.0 |
| The register — what "conformant" means | **Exists**; fetch it at a tag | `controls.yaml`, and § 0.1 |
| `register-check` — the checker | **Exists** | `src/register_check/`, run with `uv run register-check` |
| Platform prerequisites (this document, § 1) | **Exists**, manual | Below |
| A devcontainer you can copy | **Exists and has been built** — Phase 4 built it in a repository that did not author it on 2026-08-25, and the template as it stands today was built on 2026-08-30 (aarch64), which is the build the four `setup.sh` changes since then are owed | `.devcontainer/`, and § 2.0 |
| `gate-secrets` — deploys SEC-001, checks SEC-002 and SEC-003 | **Exists** | `plugins/control-register/skills/gate-secrets/` |
| `gate-quality` — deploys LNT-001, TYP-001, TST-001 | **Exists** | `plugins/control-register/skills/gate-quality/` |
| The other four `gate-*` skills | **Exists** | `plugins/control-register/skills/` |
| `register-install` — puts the checker in your repository | **Exists** | `plugins/control-register/skills/register-install/`, and § 2.3 |
| `register-adopt` — one command to deploy everything | **Exists** | `plugins/control-register/skills/register-adopt/` |
| `kind: remote` verification of platform state | **Exists**, needs a token | § 4.1 below |
| Reading the chain from a control to a blocked merge | **Exists**, needs a token | § 4.2 below |
| A CI run that **fails** when a control cannot be verified | **Exists**; give CI a credential first | § 4.3 below |

So today, adoption is: install the plugin (§ 0.0), do § 1 by hand, copy the
devcontainer, install the
checker (§ 2.3 — `/register-adopt` does it for you), run `/register-adopt`, and
run the checker with a token in the environment so the
remote blocks can be answered rather than skipped (§ 4.1). Then, in this order:
confirm your conformance run is a check a merge actually waits for (§ 4.2), give
CI a credential of its own, and only then make the run fail when it cannot
verify something (§ 4.3). That order is not a preference — turning on
`--require-complete` before CI has a credential fails every run on controls that
hold, and a check that fails for reasons nobody can act on gets ignored.

## 0 — Before you start

**This route is macOS-only.** Not by preference — `fetch-secrets.sh` reads the
macOS Keychain, and `initializeCommand` runs it before a container exists, so on
Linux or Windows the failure arrives before there is a container to read the
message in. § 2.0 states the contract a replacement owes; adapt that script
first, and everything below then applies.

### 0.a — What must already be on the machine

Nothing here is installed by any step below, and the first failure without it is
`claude: command not found` before this document's first command.

| Tool | Install | You have it when |
| --- | --- | --- |
| Homebrew | <https://brew.sh> | `brew --version` |
| Docker Desktop | <https://www.docker.com/products/docker-desktop/> | `docker info` succeeds |
| Claude Code | <https://docs.claude.com/en/docs/claude-code/setup> | `claude --version` |
| node and npm | `brew install node` | `npm --version` |
| `devcontainer` CLI | `npm i -g @devcontainers/cli` | `devcontainer --version` |
| GitHub CLI | `brew install gh`, then `gh auth login` | `gh auth status` |
| VS Code | `brew install --cask visual-studio-code` | `code --version` |

`git` and `curl` ship with macOS. Give Docker Desktop **8 GB** of memory
(Settings → Resources → Memory); the default is tight once a Python and a node
toolchain are both installed.

Two rows deliberately link rather than give a command. An install line copied
out of another project's documentation is a second copy of a fact that project
owns, free to drift the day they change it — theme **T-2**, with the drift
outside this repository's control entirely.

### 0.b — The four credentials, and where each is made

They are four different things, they are needed at four different points, and
three of them are GitHub tokens that are **not interchangeable**. Collected here
because meeting them one at a time is how the third one surprises you.

Name each PAT after **where it lives**: GitHub's token list shows the name, the
expiry and the last use and nothing else, so when both expire the name is what
tells you which one you can revoke without breaking CI.

| What | Name it | Where you make it | Scope | Where it goes | Needed at |
| --- | --- | --- | --- | --- | --- |
| Claude Code OAuth token | — | `claude setup-token` | — | Keychain, `CLAUDE_OAUTH_TOKEN` | § 2.0 — the container will not start without it |
| The repository token | `<repo>-keychain` | <https://github.com/settings/personal-access-tokens> | See § 0.b1 | Keychain, `GITHUB_TOKEN` | § 1 onward — `gh`, and `gate-repo` creating the ruleset |
| The CI token | `<repo>-actions` | <https://github.com/settings/personal-access-tokens> | `Administration: **read**` | an environment secret | § 4.3 |

**Make the last two fine-grained, not classic.** SEC-003's
`platform_token_is_not_classic` block fails on the `X-OAuth-Scopes` header a
classic token returns, so a classic one in CI is a verified violation rather
than an inconvenience. The `ghp_...` shape in § 2.0's Keychain example is a
*classic* token and is fine there — that entry is your own `gh` convenience and
never reaches CI — but do not carry the shape across to row four.

**Two tokens, and giving them names is what showed why.** An earlier version of
this table listed three — one for `gh`, one for the ruleset, one for CI — and
the first two turned out to be the same credential: `gate-repo` runs inside the
container and reads the same `$GITHUB_TOKEN` the env-file supplies, so the
"admin token" is the Keychain one and must carry `Administration: write`.

The CI token stays separate because its scope is genuinely different — it reads
platform state on every run and never writes — and because a standing credential
with `Administration: write` in CI is what
[ADR 0022](adr/0022-a-platform-token-ci-carries.md) exists to avoid.

### 0.b1 — What the repository token must carry, and how that was established

Nine permissions, and the split matters: four are needed to finish the adoption,
five are needed to work in the repository afterwards. A token with only the
first four completes § 3 and then cannot open the pull request § 1's ruleset
now requires.

| Permission | Level | Why |
| --- | --- | --- |
| Actions | read | Reading whether the conformance run passed |
| Administration | read and write | Creating the ruleset, and populating `security_and_analysis` |
| Contents | read and write | The adoption commits; pushing needs write |
| Dependabot alerts | read | Reading what SUP-002's bot found |
| Issues | read and write | The § 4.5 sweep opens and closes a tracking issue |
| Metadata | read | Mandatory on every fine-grained token |
| Pull requests | read and write | CI-001 forbids pushing to the default branch |
| Secrets | read and write | Setting the CI credential in § 4.3 |
| Workflows | read and write | Four gates write `.github/workflows/` |

**Established by measurement rather than by reading prose.** GitHub returns the
permission an endpoint requires in an `x-accepted-github-permissions` header, so
each row above was read off the live API:

```bash
gh api -i -X POST "repos/{owner}/{repo}/rulesets" 2>&1 | grep -i x-accepted-github
```

It answers `x-accepted-github-permissions: administration=write`. The `POST`
creates nothing: it carries no body, so GitHub rejects it as invalid and returns
the header anyway, which is the whole point of asking this way.

**`gh api` is what resolves `{owner}` and `{repo}`**, from the git remote where
you run it. `curl` does not: it reads braces as URL globbing and would request
`/repos/owner/repo/rulesets` literally, and answer 404 about a repository nobody
owns. Against `api.github.com` directly, substitute the real slug.

Re-derive them the same way rather than trusting this table — it is a second
copy of something GitHub states authoritatively, and the register's own rule
about second copies applies to it.

Two results are worth recording because they are counter-intuitive.

**Reading a ruleset needs only `metadata=read`.** So a `403` on
`GET /rulesets` is a *plan* limit rather than a permission problem, which is why
§ 1 reads it as one.

**`security_and_analysis` is a field-level permission, not an endpoint-level
one.** `GET /repos/{owner}/{repo}` reports `metadata=read`, and the field is
populated only for a caller with administration access. So an under-permissioned
token gets a **successful response with the answer missing** — which is why
`github_push_protection_enabled` raises `Unreadable` on an absent
`security_and_analysis` rather than reporting push protection off. A false
violation produced by not having looked is the failure that assert exists to
avoid.

**Workflows is separate from Contents and is not implied by it**, per GitHub's
own guidance: *"If your app specifically needs to access or edit Actions files
in the `.github/workflows` directory, request the 'Workflows' repository
permission."*

### 0.b2 — Where each step runs, and what a session leaves behind

**You need a git repository with a GitHub remote before § 0.1.** Everything
below assumes one: § 0.1 commits the register, § 1 calls
`gh api repos/{owner}/{repo}/…`, SEC-001 reads what git tracks and CI-001 reads what
GitHub enforces on a default branch. A folder that is not a repository fails at
the first `git` command with `fatal: not a git repository`, which reads as a
broken instruction rather than a missing precondition. The first line prints
the repository root, the second the GitHub repository these controls protect:

```bash
git rev-parse --show-toplevel
git remote get-url origin
```

Starting from nothing, `git init -b main` followed by
`gh repo create <name> --source=. --remote=origin --push` produces both. This
standard makes an existing repository conformant; creating one is not its job,
and doing it silently would put a repository on somebody's account that they did
not ask for.

**§ 0.0 runs anywhere; everything from § 0.1 runs in your repository's root.**
Installing the plugin changes your machine rather than any project — it lands in
`~/.claude/` and writes nothing into a repository. From § 0.1 onward the commands
write where you are standing, so `cd` to the repository first or you get a
register in your home directory and a `.devcontainer/` nothing will use.

Running Claude Code in the repository also creates a small amount of project
state. **No control reads `.claude/`**, so none of it changes a verdict, but one
file should not be committed:

| File | What it is | Commit it? |
| --- | --- | --- |
| `.claude/settings.local.json` | One developer's permission grants, model and output style. The format also allows an `env` block, which makes it a plausible place for a token | **No** |
| `.claude/settings.json` | The project's shared settings — hooks, and whatever the team agrees | Yes |
| `CLAUDE.md` | Only if you run `/init` | Yes, if you want one |

The shipped template's `.gitignore` cannot carry that rule: it is copied to
`.devcontainer/.gitignore`, so a `.claude/settings.local.json` line in it would
resolve to `.devcontainer/.claude/settings.local.json` and ignore nothing. Add it
to the repository's **root** `.gitignore` by hand:

```bash
echo '.claude/settings.local.json' >> .gitignore
```

**If you would rather this were checked than remembered**, add the path to
`secret_files_are_gitignored`'s `paths:` in your own register — § 3.7 is where
that starts. It is deliberately not in the shipped register: the two entries
there are files `fetch-secrets.sh` writes real credentials into, and this is a
file that merely *could* hold one.

**And a `CLAUDE.md` is linted like any other Markdown.** DOC-001's configuration
ships `ignores: []`, so a file generated by `/init` is in scope — expect to fix
a few long lines the first time the hook runs.

### 0.c — What you are about to do, and where you can stop

| # | Step | Needs anyone but you? | Can you stop after? |
| --- | --- | --- | --- |
| § 0 | Install the plugin, fetch the register | no | yes |
| § 1 | Repository visibility, ruleset, push protection | **an org or repo admin** | yes |
| § 1.1 | Install the Renovate app | **an org owner**, usually | yes |
| § 2 | Copy the template, substitute, build the container | no | yes |
| § 3 | Run `/register-adopt` | no | yes |
| § 4 | Run the checker, then credential CI | no | — |

The two rows that need somebody else are named here so you can start today and
raise them in parallel, rather than meeting them at § 1 and stopping.

## 0 — The front door

`/register-adopt` is the only entry point you need. It reads the register, works
out which controls apply to **your** repository from its files, shows a plan,
dispatches the gates in dependency order, verifies through the checker, and
commits.

```bash
/register-adopt --repo . --register ./controls.yaml
```

### 0.0 — Where `/register-adopt` itself comes from

That is a slash command, which means it is a skill, which means it is in a
plugin you have to install first. This step is here because it was the one nobody
wrote down: every instruction below assumed the plugin was already present, which
is true of the machine the standard was written on and of no other.

The repository that defines the standard is also a plugin marketplace — its
`.claude-plugin/marketplace.json` is what makes that true — and it is public, so
this needs no credential. **It stays the address**: the plugin is also published
to the `EqualExperts/ee-skills` marketplace, which is private and is where
people inside Equal Experts already look, and that is a second publication of
the same tree rather than a replacement for this instruction
([ADR 0044](adr/0044-the-adopter-installs-from-the-public-marketplace.md)). The
register, the checker and the plugin all come from one public repository, and
`tests/test_adopter_guide.py` holds this command to the address the register
names.

```bash
claude plugin marketplace add Eaiger-Ent/ee-standard
claude plugin install control-register@ee-standard
```

**How you know it worked**, and it is worth knowing the path as well as the
verdict, because § 2.0 copies a directory out of it:

```bash
claude plugin list | grep control-register
ls ~/.claude/plugins/cache/ee-standard/control-register/*/templates/devcontainer
```

The nine skills — six gates, `register-adopt`, `register-install` and
`register-variance` — are reachable as slash commands in the next session.
`/register-adopt` is the only one you invoke by hand; it dispatches the rest.
`/register-variance` is not on the adoption route at all: it reports which way a
change to gated configuration moved, and you reach for it after adoption rather
than during it.

**Install it on the host, before the container exists.** § 2.0a is the table of
what runs where, and this is the first row of it in practice: the template you
are about to copy lives in that cache, and there is nothing to copy it into yet.

**And install it again inside the container, once that exists.** The devcontainer
mounts its own `~/.claude` as a named volume, so a plugin installed on the host
is not there — `/register-adopt` reports `Unknown command` and nothing explains
why. Neither install is redundant: the host's supplies the devcontainer template
copied in § 2.0, and the container's supplies the skills that deploy the gates.
The volume outlives a rebuild, so the second install is once per project.

### 0.1 — Where `./controls.yaml` comes from

That command names a register, and until you have one there is nothing to plan
from — the skill stops and says so. The plugin does not ship one, deliberately:
the register is what a repository adopts, not what a skill installs, and yours
becomes yours the moment you edit it (§ 3.7).

Take it from a tag, and **resolve which tag rather than being told one**. A
release number written into this sentence is a copy that ages the day after it
is written, and the reader has no way to tell a current one from a stale one.
The `echo` must print something: an empty `tag` fetches nothing.

```bash
repo=https://github.com/Eaiger-Ent/ee-standard
tag=$(git ls-remote --tags --refs "$repo" | awk -F/ '{print $NF}' | sort -V | tail -1)
echo "$tag"
curl -fsSL -o controls.yaml \
  "https://raw.githubusercontent.com/Eaiger-Ent/ee-standard/${tag}/controls.published.yaml"
git add controls.yaml
```

**How you know it worked.** The second line works now; the first needs `uv` and
`register-check`, which do not exist until § 2.0 builds the container and § 2.3
installs the checker. Run the grep now and come back for the `schema` command
after § 2.3 — it is the check that matters and it is worth returning for:

In the grep's output, `ref:` names the tag you just fetched. The `schema` line
is for after § 2.3, inside the container:

```bash
grep -A2 '^    install:' controls.yaml
uv run register-check --repo . --register ./controls.yaml schema
```

The second line is the check that matters, and it is checking an invariant
rather than your typing: **the register a tag ships names that same tag** in
`tools.register-check.install.ref`, so the register and the checker it tells
`register-install` to fetch are one artefact. A `ref` naming some other tag
means you have a register from before that invariant held, and the checker you
end up with is not the one that register describes.

A tag whose register predates a field the skills need is a real failure and it
looks like your repository's fault: Phase 4 fetched the only tag that existed
and got `register-install` stopping on a missing `tools.register-check.install`,
because the tag had been cut one contract before that field landed. The `schema`
command above is what tells you which you are looking at.

**The register is committed, not vendored-and-forgotten.** It is a file in your
repository from here on, and `git log` on it is the record of every deliberate
divergence you take from the standard.

Everything in the sections below is either a step it takes for you, or a step it
tells you that you owe. Read § 1 first anyway: those are the acts no skill can
take, and a plan that reaches them is a plan waiting on you.

**What it will not do.** It writes no gate configuration itself — every artefact
is written by the gate that owns the control, which is what keeps one control's
config in one place. It will not commit on a failed verify. And it will not
report exit `3` as a pass. Whether `3` is the expected result now depends on
your environment: with a token that can read your platform state, the remote
blocks of SEC-001, CI-001 and GOV-001 are verified and a conformant repository
exits `0`; without one they report `SKIPPED (no credentials)` and the run exits
`3`. The
skill names which blocks were skipped rather than rounding up. Read § 4.1
before deciding which of the two you are looking at.

**Run it interactively, and start the session with `--permission-mode acceptEdits`.**

```bash
claude --permission-mode acceptEdits
```

Two different things make a headless or default-mode run painful, and they have
different answers.

`gate-build` writes `.devcontainer/devcontainer.json`, which Claude Code treats
as a **sensitive file**: the edit raises a prompt whatever mode you are in, and
a headless run has nobody to answer it. An allow-rule in
`.claude/settings.local.json` does **not** lift a sensitive-file guard — Phase 4
lost two runs to that before recognising it. This is a property of the harness
rather than of the standard.

Everything else — `.pre-commit-config.yaml`, the workflows, `pyproject.toml`,
`.github/dependabot.yml` — is an ordinary write, and in default mode each one
stops for approval. A full adoption is a few dozen of them. `acceptEdits`
accepts those silently and leaves the handful of guarded files still asking,
which is the checkpoint worth keeping.

**What it does not silence, and must not.** `gate-repo` asks its own question
before each API call that changes platform state, and those are the skill's
questions rather than the harness's — a permission mode does not touch them.
`tests/test_gate_repo_confirmation.py` enumerates every non-`GET` call in that
skill and fails the build if one lacks a question standing in front of it. So
the guard that matters survives every mode, including
`--dangerously-skip-permissions`.

**Read the prompts you do get.** Each write is preceded by a line naming the
control, the step, what the write does, why it is needed now and what will
verify it. Nothing has failed or passed at that moment — a gate deploys first
and verifies last — so that line is the whole of the reason you are being given.

**One confirmation, and one exception.** It asks once, covering the whole plan.
`gate-repo` asks **again** on its own, and that is right rather than redundant:
the plan covers what will be written to files, and a GitHub API call is not a
file. Its ruleset is in force the moment the call returns, for everyone with
access.

**A control is never silently absent from the plan.** Four rows cover every
control in the register — *deploy*, *dispatch elsewhere* (DOC-001 is `lint-md`'s,
in another plugin), *checked, not deployed* (SEC-002 and SEC-003 are satisfied
by what a workflow does **not** reference, so there is nothing to write), and
*manual*. A control missing from the plan would read as one that does not apply.

**It installs the checker first, and that is not a gate.** Everything it does
runs `register-check`, including the pre-flight that computes the plan, so Step 0
dispatches `/register-install` if the checker is not there. It deploys no
control, appears in no plan row and is not selectable — see § 2.3.

If you would rather deploy one gate at a time, each works standalone — § 3.1 to
§ 3.6. `register-adopt` exists to save you knowing which. Each of them needs the
checker as much as the whole family does, which is the other reason the install
is a skill of its own.

## 1 — Platform state: what only a human with admin can do

None of this is code, none of it is in a pull request, and all of it is invisible
to a `git clone`. Each row names the control it satisfies, the act, and — the
part usually missing from instructions — **how you know it worked**.

| Control | What you must do | How you know it worked |
| --- | --- | --- |
| CI-001, SEC-001 | The repository must be **public**, or on a plan whose rulesets and secret scanning are available to private repositories | `gh api "repos/{owner}/{repo}/rulesets"` returns a list. A `403 "Upgrade to GitHub Pro or make this repository public"` means neither condition holds |
| CI-001 | Create a **default-branch ruleset** requiring a pull request and passing status checks, with no bypass actors | `gh api "repos/{owner}/{repo}/rulesets" --jq '.[].name'` names it, and `gh api "repos/{owner}/{repo}/branches/$(gh api "repos/{owner}/{repo}" --jq .default_branch)" --jq .protected` is `true` — note that is the *branch* endpoint; the repository object has no such field. Then try a direct push to the default branch and watch it be refused: a ruleset nobody has seen refuse anything is not known to work |
| SEC-001 | Enable **secret scanning push protection** | `gh api "repos/{owner}/{repo}" --jq '.security_and_analysis.secret_scanning_push_protection.status'` is `enabled`. A `null` `security_and_analysis` means the plan does not offer it, or your token cannot see it |
| SUP-002 | Install a bot that proposes dependency updates, and configure it — see § 1.1 | Its first proposal, or its dashboard. Not the presence of a config file |

**The token you use matters.** Creating a ruleset needs a token with
`Administration: write` on the repository. An ordinary `GITHUB_TOKEN`, and most
fine-grained PATs, do not have it — this repository's own ruleset was blocked on
exactly that for a day. Check before you plan around it:

```bash
gh api "repos/{owner}/{repo}/rulesets" --method POST --input /dev/null 2>&1 | head -2
```

A `403` on write with a `200` on read is a permission problem, not a syntax one.

### 1.1 — Dependency updates need a bot, and possibly two

SUP-002 says dependency updates are proposed automatically. What satisfies it
depends on what your repository pins.

**Dependabot** covers package ecosystems it recognises — npm, pip/uv, Go
modules, GitHub Actions, devcontainer features. It is configured by committing
`.github/dependabot.yml`; no installation is required. Cover every ecosystem the
repository actually has, not just the obvious one.

**Dependabot cannot see a version literal embedded in a shell script or a
workflow step.** If you pin a tool with `TOOL_VERSION=1.2.3` in a setup script,
or `pip install uv==0.12.5` in a workflow, nothing proposes an upgrade for it and
the version quietly ages. It has no equivalent of a custom manager.

**Renovate** fills exactly that gap, via custom managers that read an annotation
above each literal:

```bash
# renovate: datasource=github-releases depName=gitleaks/gitleaks
GITLEAKS_VERSION=8.30.1
```

Renovate is a **GitHub App**, so it must be installed through the web at
<https://github.com/apps/renovate> — onto the organisation or the single
repository. No token can do this for you, which is why it belongs in this section
rather than in a script.

**You will run both bots, and it is not conditional.** The devcontainer template
installs uv from a pinned release, so after § 2.0's substitution your
`.devcontainer/setup.sh` holds `UV_VERSION="..."` — a version literal in a shell
script, which is exactly the case above that Dependabot cannot see. Every adopter
of this template has at least one. Treat § 1.1 as a step, not a maybe.

**Copy the config rather than writing one.** A working `renovate.json` ships with
the plugin, narrowed to the gap so the two bots do not duplicate each other:

```bash
# Installed from the marketplace in § 0.0.
cp ~/.claude/plugins/cache/ee-standard/control-register/*/templates/renovate/renovate.json .

# From a clone of the standard instead.
cp path/to/ee-standard/plugins/control-register/templates/renovate/renovate.json .
```

`{ "enabledManagers": ["custom.regex"] }` on its own — which earlier versions of
this section gave — enables the custom-regex manager and defines **no custom
manager for it to run**, so it matches nothing while looking configured. The
shipped file carries the three managers, and the patterns that go with them.

**A pattern needs an annotation to match.** `gate-secrets` writes one above every
literal it pins, and the devcontainer template ships one above `UV_VERSION`. If
you pin a tool by hand, write the annotation yourself, in `UPPER_SNAKE_CASE`
because the manager matches `[A-Z_]+=`:

```bash
# renovate: datasource=github-releases depName=owner/tool
TOOL_VERSION="1.2.3"
```

Four things about Renovate cost this repository time. They are cheap to avoid
and expensive to rediscover:

1. **Renovate reads its config from the default branch.** While `renovate.json`
   sits on a feature branch, Renovate sees an unconfigured repository — your
   config is not merely inactive, it is invisible.
2. **It will open an onboarding pull request** titled *"Configure Renovate"*,
   carrying a **default** config that enables every manager. Merging it installs
   the opposite of a narrowed config. Leave it alone: once your real config
   reaches the default branch, Renovate closes that PR itself.
3. **Do not close the onboarding PR unmerged.** That is Renovate's signal to
   disable itself on the repository.
4. **Check the Dependency Dashboard issue it creates.** It lists how many sites
   each manager matched. That count is the only external evidence the
   annotations do anything, and it is worth deriving the expected number from
   your own config and asserting it in a test — this repository found a missing
   annotation, and behind it a genuine verification defect, purely because the
   dashboard said five where six was expected.

**A bot's config file is not a bot.** An annotation with no app installed, or a
`renovate.json` on an unmerged branch, is a mechanism that exists on paper and
not in fact. Verify by looking for a proposal or a dashboard, never by looking
for a file.

## 2 — The development environment

### 2.0a — Which steps run on your machine, and which run in the container

Four things have to run on the host, and everything else has to run inside.
This is not a style preference: the whole point of the register is that every
locus reaches the *same pinned artefact*, and your host is a locus nobody
declared.

| Runs on the host | Why it cannot be inside |
| --- | --- |
| `claude setup-token`, and the Keychain entries | The Keychain is the host's, and this is what `fetch-secrets.sh` reads |
| `fetch-secrets.sh` | It **is** `initializeCommand` — it runs before a container exists |
| `devcontainer build` / `up` | There is no Docker in the container |
| Copying the template in | Nothing to copy it into until it is there |

**Everything after that goes inside**: `uv`, `register-check`, every gate,
`pre-commit`, the tests, and your commits.

Phase 4 ran the adoption on the host and it cost three things, none of which the
report showed. The host's uv was **0.8.13** where the register pins **0.12.5**,
so the run was green about a version it was not using. The `.venv` is
bind-mounted, so it is host-built or container-built and never both — switching
destroys and rebuilds it. And the pre-commit hook was never installed, while
every gate reported its `pre-commit` locus wired, because the gates read
`.pre-commit-config.yaml` and a hook is a different thing.

How you know which one you are in — the first line reports the pinned `uv`, the
second whatever your host has:

```bash
devcontainer exec --workspace-folder . uv --version
uv --version
```

If the two disagree, the container is right.

**And check the third one, because no gate will.** A wired locus is not an
installed hook: `.pre-commit-config.yaml` states intent, `.git/hooks/pre-commit`
is whether anything runs before a commit, and **every gate reads the first**.
So a repository can have six gates reporting their `pre-commit` locus wired and
nothing at all running at it.

An absent hook means nothing runs before a commit; the second line is what puts
it there:

```bash
ls -l .git/hooks/pre-commit
uv run pre-commit install
```

The template's `setup.sh` runs that install on the config's presence, so a
container built after you have a `.pre-commit-config.yaml` has the hook. A
container built before it does not, and rebuilding is what fixes that rather
than re-running a gate. This cannot become a control and will not be one:
`.git/hooks/` is untracked and CI legitimately has no hooks installed, so the
honest boundary is that the register checks the config and you check the hook.

### 2.0 — Where the devcontainer comes from

A conformant `.devcontainer/` ships with the plugin. **Where it is on your
machine depends on how you got the plugin**, and this is the first thing Phase 4
found missing from this guide — the path below is where it lives in the
repository that authors the standard, which is not a path an adopter has:

```bash
# Installed from the marketplace in § 0.0: inside the plugin's install cache.
# The version directory is the plugin's, not the register's — glob it rather
# than typing a number that moves on every plugin release.
cp -R ~/.claude/plugins/cache/ee-standard/control-register/*/templates/devcontainer \
      .devcontainer

# From a clone of the standard instead.
cp -R path/to/ee-standard/plugins/control-register/templates/devcontainer .devcontainer
```

`cp -R` on a directory that does not exist yet copies the dotfiles inside it,
which matters here: the template's own `.gitignore` is one of them, and the two
lines it carries are read by SEC-001.

Then, **in this order**:

The README documents the template rather than your project; the grep lists
every placeholder still to substitute:

```bash
rm .devcontainer/README.md
grep -rl '{{' .devcontainer
```

Delete the README first, and the order is the point: the grep matches any file
quoting the placeholder pattern, including one that only explains it, so while
that file is in the copy a clean result is unobtainable. Phase 4 substituted
every placeholder and the check still reported a file.

There are **four** placeholders, not one. `{{PROJECT_NAME}}` twice in
`devcontainer.json`, and `{{UV_VERSION}}`, `{{UV_SHA256_X86_64}}` and
`{{UV_SHA256_AARCH64}}` in `setup.sh` — uv, which every verification in this
standard runs through and which no gate can install, because a gate's own verify
step is a `uv run`
([ADR 0034](adr/0034-the-template-bootstraps-uv.md)).

**Three of the four have a source you can read; the fourth has a source you must
fetch.** The register you took in § 0.1 holds uv's version and **one** checksum,
for x86_64 — the convention `tools.gitleaks` already used. The aarch64 checksum
is not in the register and never was, so an adopter on an arm64 host who is only
told to "substitute the placeholders" has nowhere to get it. It comes from the
same release, where uv publishes a `.sha256` beside every asset:

```bash
uv_block() { sed -n '/^  uv:/,/^  [a-z-]*:$/p' controls.yaml; }
uv_version=$(uv_block | sed -n 's/^ *version: *"\{0,1\}\([0-9][^"]*\)"\{0,1\} *$/\1/p')
uv_sha_x86=$(uv_block | sed -n 's/^ *sha256: *//p')

# The other architecture's, from the release the two lines above name. `cut` is
# there because the file is `<sha>  <filename>`, and the whole line would be
# substituted into a shell assignment.
rel="https://github.com/astral-sh/uv/releases/download/${uv_version}"
uv_sha_arm=$(curl -fsSL "${rel}/uv-aarch64-unknown-linux-gnu.tar.gz.sha256" | cut -d' ' -f1)

# All three non-empty, or the substitution below is a silent no-op.
echo "${uv_version:?} ${uv_sha_x86:?} ${uv_sha_arm:?}"
```

**Verify the one you fetched against the one you were given.** The x86_64
checksum exists in two places now — the register's and the vendor's — and the
whole point of a pinned release is that they agree:

```bash
test "$uv_sha_x86" = \
  "$(curl -fsSL "${rel}/uv-x86_64-unknown-linux-gnu.tar.gz.sha256" | cut -d' ' -f1)"
```

Then substitute all four, and commit the result:

```bash
sed -i.bak \
  -e "s/{{PROJECT_NAME}}/$(basename "$PWD")/g" \
  .devcontainer/devcontainer.json
sed -i.bak \
  -e "s/{{UV_VERSION}}/${uv_version}/g" \
  -e "s/{{UV_SHA256_X86_64}}/${uv_sha_x86}/g" \
  -e "s/{{UV_SHA256_AARCH64}}/${uv_sha_arm}/g" \
  .devcontainer/setup.sh
rm .devcontainer/*.bak
grep -rl '{{' .devcontainer
```

The final grep should print nothing.

`-i.bak` and the `rm` are there for portability rather than caution: BSD `sed`,
which is what a macOS host has, requires an argument to `-i` where GNU `sed`
requires its absence.

**Check that echo.** The first version of these commands used `grep -A4`, which
never reached `version:` because the register comments that block — so they
returned empty, `sed` substituted nothing, and the placeholders survived into a
container that then failed at `sha256sum -c`. An extraction that quietly yields
nothing is worse than one that errors.

**Substitute them as they are, quotes and all.** The template ships
`UV_VERSION="{{UV_VERSION}}"` quoted because that is what `shellcheck` wants,
and both readers of that line take it: `tool_versions_match_register` matches an
optional quote after the separator and is case-insensitive, and the
`# renovate:` annotation above the pin is read by a custom manager whose pattern
accepts one too. An earlier version of this section said to substitute
*unquoted*, which was true of the assert for one week in August 2026 and has not
been true since — following it now would mean deleting quotes the template put
there deliberately.

**Do not change the case either.** Script-level shell variables in this template
are `UPPER_SNAKE_CASE`, and that is the one spelling Renovate's custom manager
matches (`[A-Z_]+=`). The checker does not care; the bot does, and a pin the bot
cannot see never moves.

**If your repository has a Python ecosystem, write `.python-version` now.** The
template is language-agnostic — `setup.sh` branches on `package-lock.json`,
`uv.lock` and `poetry.lock` — so it ships no toolchain file, and
`tools.python` in the register declares `source: toolchain` with
`toolchain: .python-version`. `tool_versions_match_register` fails a
toolchain-sourced tool whose file git does not track, so without it SUP-001
fails on a file nothing has told you to write:

Write the version your project runs on. The last line is for after § 2.3:

```bash
echo "3.14" > .python-version
git add .python-version
uv run register-check run --control SUP-001
```

Pin it rather than relying on `requires-python`: a support floor constrains and
a toolchain file **selects**
([ADR 0027](adr/0027-the-interpreter-is-a-pinned-tool.md)). Repositories with no
Python ecosystem write nothing here — the register records the file for the tool
it names, and a tool your repository does not have is not checked.

Then run `/gate-build` to pin what you chose and stamp it.

**Before the first `devcontainer up`, populate the host Keychain.**
`initializeCommand` runs `fetch-secrets.sh` on your machine and exits `1` when
there is no Claude Code OAuth token, so the container never starts and the
message arrives before you have a container to read it in:

```bash
# These service names carry no project prefix, so one credential store serves
# every ee project on the machine — a second adoption finds them already set.
security find-generic-password -a "$USER" -s "CLAUDE_OAUTH_TOKEN" -w >/dev/null \
  && echo "already set" || echo "not set"
```

**What follows is three commands run one at a time, not a block to paste.** The
first is interactive and the third needs what it printed, so pasting all three
runs the third with nothing to put in it — and stores the literal placeholder,
which fails the build later with no visible connection to the cause.

First, get the token. This opens a browser, waits for you to authorise, and then
prints the token. Copy what it prints:

```bash
claude setup-token
```

Then clear any existing entry. `add-generic-password` will not overwrite — on an
existing entry it fails with *"The specified item already exists in the
keychain"* — and the redirect makes this harmless when there is none:

```bash
security delete-generic-password -a "$USER" -s "CLAUDE_OAUTH_TOKEN" 2>/dev/null
```

Last, store what the first command printed, replacing the placeholder and its
angle brackets:

```bash
security add-generic-password -a "$USER" -s "CLAUDE_OAUTH_TOKEN" -w "<paste it here>"
```

A GitHub token is optional here, but `gh` needs it:

```bash
security add-generic-password -a "$USER" -s "GITHUB_TOKEN" -w "<a token>"
```

Either name may be prefixed with your checkout directory in `UPPER_SNAKE_CASE`
to scope it to one project. `check-auth.sh` reports which entry answered on
every container start.

**Those three commands are macOS**, and `security` is the reason: the shipped
`fetch-secrets.sh` reads the macOS Keychain, so on Linux or Windows the script
is what you adapt, not the instructions around it. Say so plainly rather than
letting an adopter discover it at `initializeCommand` — the failure arrives
before there is a container to read the message in, which is the worst place a
platform assumption can surface.

What a replacement owes the rest of the template is a **contract, not a
mechanism**: run on the host, read from whatever store your platform has —
`secret-tool` on a Linux desktop, `pass`, a cloud secret manager, an
already-exported environment variable — and leave two files behind.

| File | Read by | Shape |
| --- | --- | --- |
| `.devcontainer/.env` | `check-auth.sh`, with `set -a; . .env` | Shell. A value containing a space **must** be quoted, or the shell splits it |
| `.devcontainer/.env.docker` | Docker, via `runArgs --env-file` | Verbatim after the `=`. The same quotes would land *inside* the value, so this copy has them stripped |

`CLAUDE_CODE_OAUTH_TOKEN` is the one required name and the one whose absence
should exit `1`; `GITHUB_TOKEN`, `GIT_AUTHOR_NAME` and `GIT_AUTHOR_EMAIL` are
written only when the store answers. Derive the second file from the first
rather than writing both — the shipped script ends with the one `sed` that does
it, and two writers is two spellings of one secret.

Both files must stay gitignored. That is not housekeeping either: the
`.gitignore` that came with the copy names them, and **SEC-001 reads exactly
those lines**.

**Adding a feature means rebuilding, not restarting.** `devcontainer up` reuses
an existing container and the lock file is regenerated only on a build, so the
lock ends up covering the features you had rather than the ones you declared —
which is exactly the partial lock DEV-001 fails:

```bash
devcontainer up --workspace-folder . --remove-existing-container
```

**Why it ships here rather than as a template repository.** The template
repository this standard grew from is private and is not a GitHub template, so
anyone whose access lapses loses the ability to start a project. A directory in
the plugin is obtainable by anyone who can install the plugin, which is how the
first repository outside this one obtained it.

**There is no configure-it-for-your-stack step, and no skill that performs one.**
The template is already configured: the image is pinned by digest, the features
are declared, and the lock file covers them. If its image does not fit your
stack, change the image yourself before running `/gate-build`, which pins what it
finds and fails you if you left a floating tag
([ADR 0037](adr/0037-the-template-is-the-whole-devcontainer-step.md)).

**What the template pins**: the image by digest, and every feature by digest in
`devcontainer-lock.json`. **What it refuses to pin**: any tool version inside
`setup.sh`. That is Phase 2's own exit criterion — *the template pins no tool
version by hand; every tool it installs is either sourced from a lockfile the
consumer repo already commits, or from a single toolchain file*. A template
scattering pins through a shell script reproduces that problem in every
repository that adopts the standard, and you have no
`tool_versions_match_register` of your own until you adopt the register too.

So `setup.sh` installs only from lockfiles you commit. Scanners, linters and
analysers are installed by the gates that own their controls, each writing its
own stamped region into that file.

**Two lines that must survive the copy.** The template's own `.gitignore` names
`.env` and `.env.docker`, and SEC-001 reads them. Deleting the file fails
SEC-001, as does moving the rule somewhere git does not track — an uncommitted
`.gitignore` or a `.git/info/exclude` entry protects your clone and nobody
else's. Until register contract 18 it failed nothing at all: it failed quietly,
later, in someone else's clone, and a secret that reaches a remote is not undone
by removing it.

**How you know it worked**, in this order:

The grep should print nothing, the `uv --version` line proves the bootstrap
actually ran, and the last control checks the `.gitignore` that came with the
copy:

```bash
grep -rl '{{' .devcontainer
devcontainer build --workspace-folder .
devcontainer exec --workspace-folder . uv --version
uv run register-check run --control BLD-001 --control DEV-001
uv run register-check run --control SEC-001
```

The `uv --version` line is there because Phase 4 built a container that reported
every credential green and had no uv in it, while this template's own `setup.sh`
called `uv sync --frozen` a few lines down. A container in which nothing can be
checked passes every check you can run in it.

A fresh copy fails the loci and stamp blocks of both controls, which is correct:
`gate-build` has not run yet. It should pass `devcontainer_user_is_non_root`,
`devcontainer_image_digest_pinned` and `devcontainer_lock_covers_all_features`
from the first line.

This repository's own `.devcontainer/` is the worked example the template was
generalised from; its operator guide is
[`06-devcontainer-setup.md`](06-devcontainer-setup.md), and the specification
both meet is [`03-devcontainer.md`](03-devcontainer.md).

What matters when you adapt the copy:

- **Pin the image by `@sha256:` digest**, not by tag. A tag moves.
- **Commit `devcontainer-lock.json`, covering every feature.** A lock file that
  covers three of four features reads as solved and is not.
- **State the user.** `remoteUser` or `containerUser`, and not root. A
  devcontainer naming neither runs as whatever its base image happens to use,
  which may change under you on any digest bump (BLD-001).
- **Install nothing unpinned and nothing unverified.** A version-pinned download
  whose checksum you verify beats a devcontainer feature that fetches a release
  without verifying it — and most community features do not verify. See the
  preference ladder in [`03-devcontainer.md`](03-devcontainer.md), which was
  corrected for exactly this reason: a lock file pins the *installer's* digest,
  not the artefact that installer fetches.
- **Keep secrets out of the repository.** This repo's `.env` — and the
  `.env.docker` derived from it for `--env-file` — are gitignored and populated
  from the host keychain by `fetch-secrets.sh`. SEC-001 reads those lines, so a
  second secrets file means a second line **and** a second entry in that
  control's `paths:` — a file the register does not name is a file nothing
  checks. One line per path, never a glob: a glob that later misses a file
  gives no signal, and the per-path form makes the omission visible.

### 2.1 — Take back the editor locus from the features

A devcontainer feature contributes VS Code extensions **and settings**, and
`features:` is the part of `devcontainer.json` a reviewer reads as already
governed because DEV-001 pins it. The pin covers what a feature installs. It
says nothing about what a feature configures, which is unreviewed and arrives
anyway.

The two you will meet:

| Feature | Extensions | Settings |
| --- | --- | --- |
| `python:1` | `ms-python.python`, `ms-python.vscode-pylance`, `ms-python.autopep8` | `python.defaultInterpreterPath`, and `[python].editor.defaultFormatter` = **autopep8** |
| `node:2` | `dbaeumer.vscode-eslint` | — |

So a repository whose LNT-001 pins ruff formats Python with autopep8 until it
says otherwise. Until register contract 21 `linter-wired-at-all-loci` did not
catch it: the assert read `editor_extension` from `stacks:` and asked whether
the pinned extension was *present*, and presence does not exclude — both
extensions were installed.

**From contract 21 it does catch it, and it will fail you for saying nothing.**
`stacks.<stack>.gates.<role>` now carries an `editor_binding`, and the assert
reads the binding rather than the install:

| What it finds in `.vscode/settings.json` | Verdict |
| --- | --- |
| The language bound to the pinned extension | pass |
| The language bound to another extension | fail — names what holds it |
| No binding at all | **fail** — whatever a feature contributes decides |
| A binding here *and* in `devcontainer.json` | fail, agreement included |

The third row is the one to plan for. An absent binding is not a neutral
default: it is the exact state the autopep8 case occurred in, where no tracked
file said anything and the feature decided. Stating it is the requirement, not
a way of correcting something. The fourth is unintuitive and deliberate —
a duplicate in `devcontainer.json` agrees today by luck, under a merge rule the
specification declines to state.

`/gate-quality` writes this file for you. Doing it by hand is the same content.

**Put the binding in `.vscode/settings.json`, not in `devcontainer.json`.** The
containers.dev merge table gives one instruction for the `customizations`
property — *"Merging is left to the tools"* — where every other property states
a rule. A setting written into `devcontainer.json` lands in the same
machine-scoped file as the feature's and competes with it on undefined terms.
Workspace settings outrank machine settings by documented rule, and the file is
tracked, so it reaches a diff and a review. The reasoning is
[ADR 0029](adr/0029-the-editor-locus-is-configured-by-the-repository.md).

```jsonc
{
  "[python]": { "editor.defaultFormatter": "charliermarsh.ruff" },
  "ruff.importStrategy": "fromEnvironment",
  "python.analysis.typeCheckingMode": "off"
}
```

The last line is TYP-001's: Pylance ships with the feature and reports
diagnostics from its own rules, which is a second type checker beside the mypy
your register pins. Turning its verdicts off keeps it as a language server —
completion, navigation, hover — and stops it being an opinion.

**How you know it worked.** Ask the checker, which is the same question your
CI will ask:

```bash
uv run register-check run --control LNT-001
```

Then confirm it in the editor, because the checker reads a file and the editor
is what a developer meets: open a Python file, run *Format Document*, and check
the status bar names ruff.

```bash
code --status | grep -i autopep8
```

Installed is fine; formatting is not.

The extension staying installed is expected — `devcontainer.json` offers no way
to remove what a feature contributes, and this is a configuration fix rather
than an installation one.

**If your project environment is not at `.venv/`**, name it here too:
`"python.defaultInterpreterPath": "${env:UV_PROJECT_ENVIRONMENT}/bin/python"`
reads back a path set once in `containerEnv`, rather than repeating it.

**Better, if your stack allows it: do not install the feature.** Everything
above is a correction applied after the fact, and
[ADR 0030](adr/0030-uv-is-bootstrapped-from-a-pinned-release.md) removes the
cause instead. Ask what the feature is for. If it is there so that something can
run `pip install uv`, it is not needed: uv is a single static binary that
requires no Python, and `uv sync` fetches the interpreter your `.python-version`
names. Install uv the way you install any other pinned tool — the release
tarball for the container's architecture, verified against the `.sha256` the
vendor publishes beside it — then delete
`ghcr.io/devcontainers/features/python:1` from `devcontainer.json` and its entry
from `devcontainer-lock.json`.

Three extensions stop arriving and both settings stop being written. **Do not
expect one interpreter to be left.** Doing this here uncovered
`python3-minimal` in `mcr.microsoft.com/devcontainers/base:trixie`, which the
feature had been sitting in front of on `PATH`: a bare `python3` still answered,
one minor version below the pin (ADR 0030 revision 2). Check yours with
`bash -lc 'command -v python3; python3 -V'` after the rebuild, and expect an
answer. What makes it harmless is not its absence but § 2.2's rule. The cost is
Pylance: Python completion, navigation and hover go with it. Add
`ms-python.python` back to `devcontainer.json` if you want it — as a line
someone reviewed, which is the difference between choosing it and inheriting
it.

**Do not reach for a leaner base image.** It is the obvious suspicion and it is
wrong. `mcr.microsoft.com/devcontainers/base:trixie` is Debian plus
`common-utils:2` and `git:1`; it declares no `customizations` and contributes no
extensions and no bindings. Every extension in the container comes from a
feature the repository listed itself. A leaner base removes none of them, and
costs you the non-root `vscode` user BLD-001 stands on.

### 2.2 — Scripts reach the interpreter through uv, not through `PATH`

Give every tracked script this shebang, whatever language it is a script for:

```python
#!/usr/bin/env -S uv run python
```

`.python-version` binds what goes through uv, and a shebang does not: the kernel
resolves it against `PATH`, so `./scripts/whatever.py` runs on whichever
interpreter is first there. Here that was a devcontainer feature's, one minor
version below the pin, while mypy and ruff checked the same file at the pinned
version — for six days, silently, because the two numbers were close enough to
agree on everything anyone happened to run
([ADR 0028](adr/0028-the-support-floor-is-what-we-run.md) revision 2).

This is the rule to copy, not the container fix that accompanied it. It holds
where you control no image at all — a developer running a tracked script on
their host, a CI job whose runner brings its own Python — and it keeps holding
after you remove a feature, which as § 2.1 says does not leave you with one
interpreter. `tests/test_toolchain_pin.py` here fails any tracked script whose
shebang resolves from `PATH`; copy it, or write the equivalent, because the
failure it catches is invisible until a version difference finally matters.

### 2.3 — The checker itself, and where it comes from

Everything below this line runs `register-check`: the pre-commit hooks for
SUP-003, BLD-001 and DEV-001, the CI job CI-001 requires, every gate's own
verify step, and your audit in § 4. None of them installs it.

```bash
/register-install --repo . --register ./controls.yaml
```

It adds one dependency, pinned to a tagged ref of the repository that defines
the standard:

```text
register-check @ git+https://github.com/<owner>/<repo>@v<x.y.z>
```

**Where every part of that comes from.** The repository and the tag are the
register's `tools.register-check.install`; the grammar that joins them to a
package name is `ecosystems.<name>.git_dependency`, because PEP 440's direct
reference is a fact about Python rather than about this standard. Point the
first at a fork or an internal mirror and nothing else changes. If your
ecosystem has no `git_dependency`, the skill stops and says so rather than
guessing a spelling — today only `python` has one, and
[ADR 0032](adr/0032-the-checker-is-installed-from-a-tagged-ref.md) § The
non-Python adopter is not solved records that as known rather than pending.

**A tag, never a branch.** An unpinned git dependency resolves to whatever the
default branch says today — the same defect DEV-001 refuses in an image tag and
SUP-003 in an action ref. Without the pin the checker would be the one tool in
your repository that could change under you between two runs of one commit.

**Reach it through your package manager, not off `PATH`.** `uv run
register-check`, not `register-check`. A bare name resolves against `PATH` and
would report success against some other copy entirely
([ADR 0020](adr/0020-a-locus-reaches-the-pinned-artefact.md)), which is the same
failure this guide describes for `npx --no-install` in § 3.

**Every command in this document obeys that**, which it did not until the rule
was checked against the examples rather than only stated beside them: two
copy-and-paste blocks and sixteen inline mentions spelled the bare name, so a
reader following the guide reached for `PATH` on the guide's own instruction.
`tests/test_adopter_guide.py` now fails a fenced block that does it again.

**Two things about this are not settled**, and are worth knowing before you
depend on them. Whether Dependabot or Renovate proposes a bump for a
`git+https` dependency pinned to a tag is **not verified** — if neither does,
your pin rots at a known version, which is a different failure from an unpinned
one and not a better one. And this repository is public, which is what makes the
install need no credential; that is load-bearing rather than incidental.

**No `ee-control:` stamp is written here**, and that is the decision rather than
an omission. A stamp names a control and the gate that deployed it, and no
control says *the checker is installed* — SUP-001, SUP-002 and SUP-003 are about
lockfiles, update proposals and frozen installs. The checker being present is
what makes all three *checkable*, which is a different claim.

`/register-adopt` dispatches this first, before its own pre-flight, so if you
came through § 0 it has already happened. It is here as its own step because a
guide that assumed the instrument was present is how the gap went unnoticed for
as long as it did: inside the repository that defines the standard, `uv run
register-check` resolves because the project being run is the project being
checked.

## 3 — The gates

All six gates are built — see § 3.1 to § 3.6, and § 0 for the front door that
dispatches them in order. DOC-001 is the one control no gate here deploys: it is
`lint-md`'s, in another plugin.

**And that plugin is one you may not be able to install.** `lint-md` lives in
the `EqualExperts/ee-skills` marketplace, which is **private**. If your account
cannot reach it, no skill deploys DOC-001 for you — the plan names it *dispatch
elsewhere*, and elsewhere is somewhere you cannot go.

**So you deploy it by hand, and the checker verifies it.** That is a decision
rather than a stopgap
([ADR 0044](adr/0044-the-adopter-installs-from-the-public-marketplace.md)): the
six steps below are the supported route for an adopter who cannot reach
`ee-skills`, and `register-check` runs the same two verify blocks over what you
write as over anything a gate writes, because a control is verified by what your
repository contains and not by what put it there. DOC-001 is **the one control
an outside adopter satisfies by hand**, and it is one control's worth of extra
work, written here rather than discovered.

Two routes were rejected and are worth knowing about, because both look
reasonable. **Copying `lint-md` into your repository** is what Phase 4 did, and
it is recorded as what happened rather than as a recommendation: a copy of
someone else's skill, in your repository, going stale with no line to read on
the day it stops matching upstream — and `register-check deployments` cannot
reconcile it, because a copied directory is not an installed plugin. **A DOC-001
gate in this plugin** would fork one lifecycle into two implementations free to
drift, which is the duplication this standard exists to prevent, one level up.

The good news, which is not obvious: **DOC-001 asks for no provenance stamp.**
Its verify blocks are the tool itself and `markdown_gate_wired_at_all_loci` —
there is no `provenance_stamp_present`, so a hand-wired deployment passes the
control completely rather than passing it in part. `deployed_by: lint-md` only
matters where a stamp is read, and here nothing reads one. **Do not write a
stamp naming `lint-md`**: a stamp names the skill that deployed the artefact, and
recording a deployment that did not happen is worse than recording none.

Seven steps. Six were done in Phase 4's consumer repository; the seventh — the
editor locus — was missing from this list until an adopter deployed the other six
and the gate said so, and all seven are now verified together in a repository
that had none of them. The lockfile is the pin:

```bash
npm init -y && npm install --save-dev markdownlint-cli2
```

1. `package-lock.json` — commit it. The register declares this tool
   `source: lockfile`, so there is no version to write anywhere else.
2. `.markdownlint.yaml` — the rule set, with `MD013.line_length` at or under the
   register's ceiling. DOC-001 is `narrowing-only`: tighten, never loosen.
3. `.markdownlint-cli2.yaml` — `gitignore: true` and `ignores: []`. The first
   scopes the tool to what git does not ignore, which is not an exemption; the
   second stays empty, because per
   [ADR 0019](adr/0019-exemptions-cannot-hide-tracked-files.md) an exemption may
   never hide a tracked file, and `markdown_gate_wired_at_all_loci` fails one
   that does.
4. **A root `.gitignore` containing `node_modules/`.** This is the step that
   looks like housekeeping and is not: `gitignore: true` is only as good as your
   `.gitignore`, and without this line the linter walks every third-party README
   under `node_modules` and DOC-001 fails on somebody else's markdown. Phase 4's
   consumer had no root `.gitignore` at all — nothing in this standard writes
   one — and staged 1,542 files before anyone noticed.
5. A `pre-commit` hook whose `entry` is `node_modules/.bin/markdownlint-cli2`,
   never `npx --no-install`.
6. A CI job **whose id is `lint-md`**, running the same binary. That string is
   what CI-001's `required_checks:` names, and GitHub matches a required check
   by the context a job produces — rename the job and your ruleset waits forever
   for a check nothing reports.
7. **The editor extension the register names**, in
   `.devcontainer/devcontainer.json` under `customizations.vscode.extensions`.
   DOC-001 declares **three** loci and this is the third: `editor_extension:` in
   its `args:` is the id, read from the register rather than typed from memory.
   Installing it is all that file does for this locus — which tool holds a gated
   file type is settled in `.vscode/settings.json` (ADR 0029).

This step was missing from the list until an adopter deployed the other six and
`markdown_gate_wired_at_all_loci` answered *"editor locus — no editor
configuration installs …"*. The table below had it the whole time and is headed
as **this repository's** artefacts, which reads as reference rather than
requirement. A control's loci are the requirement.

**The PostToolUse hook in that table is not a seventh thing to write.** The
assert judges a hook script only where one runs this tool, so a repository with
none passes; a repository whose hook invokes something other than what the
register pins does not.

Then `uv run register-check run --control DOC-001`, which is what makes this a
deployment rather than a hope.

**And re-run `/gate-supply-chain` afterwards.** Step 1 gave the repository a
`package.json`, which is a **node ecosystem** it did not have before, and SUP-002
requires an update channel for every ecosystem present — so a repository that was
green on SUP-002 fails it the moment DOC-001 lands, with
*"`.github/dependabot.yml` does not cover: node"*. That file is
`gate-supply-chain`'s and carries its stamp, so re-running the gate is the route:
adding the entry by hand would leave a stamp claiming work the gate did not do.

Found by the first adopter to deploy DOC-001 into a Python-only repository, which
is what every adopter following this guide has.

What follows describes this repository's own artefacts, which are the reference
implementation:

| Locus | File here | What it gives you |
| --- | --- | --- |
| editor | `.devcontainer/devcontainer.json` → `customizations.vscode.extensions` | The same rules while you type |
| editor | `.claude/hooks/md-lint.py` | Lint on write, via a PostToolUse hook |
| pre-commit | `.pre-commit-config.yaml` | The same rules before a commit |
| ci | `.github/workflows/lint.yml`, `.github/workflows/register-check.yml` | The same rules before a merge |

The discipline is **pin once, reference many**: the same tool version and the
same configuration at every locus. Where a package manager can own a version, let
it — `package-lock.json` pins `markdownlint-cli2` here, so there is no version to
keep in step.

**Invoke the artefact, not the name.** Every locus here runs
`node_modules/.bin/markdownlint-cli2`, because `npx --no-install` does *not* mean
"resolve locally" — with no local install it answers from the npx cache or the
registry, never from your lockfile, which makes that lockfile an authority in
name only ([ADR 0020](adr/0020-a-locus-reaches-the-pinned-artefact.md)). A
**bare** `markdownlint-cli2` is worse again: that one does resolve from `PATH`,
so whatever is installed on the machine answers. Measured at npm 11.17.0 on
2026-08-29; the ADR's § Re-measured has the table and the versions, because
which wrong binary you reach depends on your npm and *that* you reach one does
not. The register
records that path as `tools.<tool>.invocation` and the checker holds every locus
to it. A missing local install is then `UNCLASSIFIED — cannot verify`, which is
the honest answer, rather than a pass earned by a binary nobody pinned.

### 3.0 — Two local loci, one file, and the hook type nobody installs

From register contract 31 the register has a fourth locus, `pre-push`
([ADR 0039](adr/0039-a-push-is-a-locus.md)), and in the register this
repository ships it is declared by TST-001, SUP-001, SUP-002 and — from
contract 32 — SEC-002. Those four had `ci` as their only locus, so the test
suite, two supply-chain controls and the one that forbids a static cloud key in
a workflow were all verified nowhere you could reach before opening a pull
request.

**SEC-003 does not declare it, and the omission is the rule rather than an
oversight.** Its `kind: remote` blocks answer only inside a GitHub Actions job,
so `register-check run --control SEC-003` exits `3` on your machine — a hook
running it would refuse every push. The test for whether a control can take this
locus is whether your own machine can *finish* verifying it.

**It lives in `.pre-commit-config.yaml`, beside the `pre-commit` locus.** Both
moments are hooks in that one file and a hook's `stages:` key says which it
belongs to. Three things follow, and each of them has bitten:

1. **Install both hook types.** `pre-commit install` writes
   `.git/hooks/pre-commit` and nothing else, so a repository can have the locus
   wired in the config, reported as wired by every gate, and running nothing —
   the half-state § 2.0a already records for the first hook, one moment later.
   Run `pre-commit install --hook-type pre-commit --hook-type pre-push` through
   whichever package manager your lockfile pins `pre-commit` in. The shipped
   `setup.sh` does it at container-create, and `check-auth.sh` reports either
   one missing on every container start. **No control checks this**, and cannot:
   `.git/hooks/` is untracked and CI has no hooks installed.
2. **Keep the `stages:` key your gate writes.** A hook naming no stage runs at
   every stage you have installed — pre-commit's own rule — so dropping it from
   the test hook runs your whole suite on every commit, and adding it to a
   pre-commit hook stops that hook running at commit time. Setting
   `default_stages: [pre-commit]` at the top of the file is worth the one line:
   it makes *a hook that says nothing is a pre-commit hook* true, which is what
   the register's `locus:` list already claims.
3. **The pre-push hook names its controls.** It runs
   `register-check run --control …` rather than a full audit, and that is forced
   rather than tidy: if any control in your register carries a `kind: remote`
   block, a full local run exits `3` because your machine holds no platform
   credential — so a hook auditing everything would refuse every push. Do not
   "fix" that by tolerating `3` in the hook; a locus that accepts an incomplete
   run accepts one that verified nothing.

**What you get for it.** `git push` runs what would otherwise fail in CI half an
hour later. Judge it the way this repository did: delete a passing test, commit,
and watch the push refuse.

### 3.1 — `gate-secrets`, and what it needs from you first

`/gate-secrets` wires SEC-001 at both its local loci, wires SEC-002 at its
pre-push and ci loci from register contract 32, and checks SEC-003. It
takes `--repo` and `--register`, the same two flags as `register-check`, so a
deployment and its audit cannot be pointed at different things by accident.

**SEC-002 used to be checked and never deployed, and that changed.** It is still
satisfied by an *absence* — no workflow naming a static cloud key — but an
absence still needs something that notices when it stops being true, and until
contract 32 nothing local did. The gate now writes one hook and one CI step for
it and stamps both. If your plan still shows SEC-002 as *verify only*, the plan
was built from an older register.

**Three prerequisites, and how you know each is met.**

| Prerequisite | Why | How you know it worked |
| --- | --- | --- |
| A register the skill can read | Every value it writes — the scanner's name, version, checksum and release repository — comes from `controls.yaml`. There is no default, because a default is a decision nobody recorded | `uv run register-check --repo . --register <path> explain SEC-001` prints the control |
| `tools.<scanner>.release_repo` set in your register | The skill downloads a pinned release and needs `owner/name`. Before Phase 2 this value existed only inside a `# renovate: depName=` comment, which is an annotation for a bot rather than a field anything can read | `uv run register-check schema` accepts the register; a malformed value is rejected as *must be an owner/name repository reference* |
| A workflow that runs on `push` or `pull_request` | A workflow triggered only by `workflow_dispatch` runs when a human clicks it, and a control reachable only that way is declared and unreachable | The verify step reports `ci locus — no gating step runs '<scanner>'` if you have none |

**SEC-001's third block asks GitHub, and needs a token that can see the answer.**
Its remote block reads whether secret scanning push protection is enabled. With
no token it reports `SKIPPED (no credentials)`; with a token that lacks
repository administration read access it reports `UNCLASSIFIED`, because GitHub
omits the setting from that answer entirely and an absent setting is not a
setting that is off (§ 4.1). Either way the run exits `3` and the two local loci
are still verified. Enabling push protection is the platform act in § 1 that
only an admin can take.

**Two ways an adopter who already had SEC-001 passing can now fail it.**

1. **The CI locus is checked.** SEC-001 declares three loci and, before Phase 2,
   only the pre-commit hook was read — a repository could delete its
   secret-scanning job and stay green. If your scanner runs only at pre-commit,
   SEC-001 now fails naming the ci locus. That is the check working.
2. **Your ignore file is judged by what it hides.** An entry whose fingerprint
   names a file **git tracks** hides authored content from a control with
   `variance: forbidden` and `baseline: null`, and fails
   ([ADR 0019](adr/0019-exemptions-cannot-hide-tracked-files.md)). An entry
   naming a path git does not track — a vendored directory, a fixture outside
   the repository's own content — scopes the scanner and is fine. Deal with what
   the first kind was hiding; do not move it somewhere quieter.
3. **The files that hold fetched credentials must be ignored, by a rule git
   carries.** Register contract 18 added `secret_files_are_gitignored`, and it
   reads the `paths:` your register names. Three ways it fails, and the remedy
   differs for each. *Not ignored* — add the rule. *Ignored by something git
   does not track*, meaning `.git/info/exclude`, a global excludes file, or a
   `.gitignore` nobody committed — the rule protects your clone and no other, so
   commit one that travels. *Already tracked* — an ignore rule added now removes
   nothing from history; treat what is in that file as disclosed, rotate it, and
   deal with the history separately. `gate-secrets` writes the first, reports the
   second, and refuses to paper over the third.

   This was the last part of SEC-001 resting on prose. Both this repository's
   `.gitignore` and the shipped devcontainer template carried a comment saying
   *SEC-001 depends on these two lines*, and nothing read either.

**Wiring by hand instead?** Then stamp what you write. SEC-001's verify reads
back a provenance stamp naming SEC-001 and the gate that deploys it, so a
hand-wired hook with no stamp fails. Say in the stamp's comment that it was
adopted rather than deployed — this repository's own artefacts do exactly that,
because they were written in Phase 0.5 before there was a gate to write them,
and a stamp claiming otherwise would be a record of something that did not
happen. The `.gitignore` region is the newest of them, stamped at contract 18
rather than rewritten, for the same reason.

**SEC-003: every secret your workflows reach must be named in your register.**
Register contract 22 added the control and the `platform_credentials:` block it
reads ([ADR 0022](adr/0022-a-platform-token-ci-carries.md)). It is an
allow-list, and that is the opposite direction from SEC-002's `cloud_credentials:`
deny-list: a name SEC-002 has not heard of passes, and a name SEC-003 has not
heard of fails. So a register with no `platform_credentials:` block permits no
secret at all, and a repository whose workflows use `${{ github.token }}` — as
most do — fails until it names `GITHUB_TOKEN`:

```yaml
platform_credentials:
  - name: GITHUB_TOKEN
    triggers: any               # `any`, or a list of workflow events
    max_lifetime_hours: 24
```

Three things fail it, and the remedy differs for each. A secret **nothing
names** — write the entry, which is the point: a credential nobody wrote down is
a credential nobody decided. A named secret under an **event its entry does not
permit** — either widen `triggers` deliberately or stop reaching the secret from
that event; a workflow that added `pull_request:` in order to reach a standing
credential is the case this exists to catch, and it cannot be caught by a guard
written in the file the pull request is editing. And `secrets: inherit`, which
hands a called workflow every secret you hold — no allow-list can enumerate
that, so name what the called workflow actually needs and pass those.

**And SEC-003 refuses a classic personal access token outright** (contract 24).
`X-OAuth-Scopes` comes back for a classic token and for no other kind, so its
presence identifies the instrument — including a classic token with no scopes,
where the header arrives empty. Issue a fine-grained token instead; that is the
difference the whole arrangement rests on, since a classic one reaches every
repository its owner can. Note what this does **not** check: no API lets a
fine-grained token enumerate its own permissions, so *scoped to this repository,
`Administration: read` only* stays a human act you record when you issue it.

**SEC-003 also asks GitHub when your CI credential expires.** From register
contract 23 it carries a `kind: remote` block reading the
`github-authentication-token-expiration` header against the largest
`max_lifetime_hours` your register permits. It answers **only inside a GitHub
Actions job**: the token in your shell is not the one CI carries, so anywhere
else it reports `UNCLASSIFIED` and the run exits `3`. That is the honest state
rather than a fault — a control answered from the wrong credential would be
worse than one not answered.

**If you are about to give CI a platform token, read ADR 0022 first.** It sets
out four options and recommends a different one for you than this repository
takes: an adopter's contributors are not organisation owners, so the credential
belongs behind a deployment environment whose branch policy a pull request
cannot edit, rather than in a plain repository secret. It also states the
ordering that is not negotiable — the register must be able to see the
credential *before* the credential exists, which is what SEC-003 and
`platform_credentials:` now make possible.

### 3.2 — `gate-quality`, and the three controls it deploys together

`/gate-quality` wires LNT-001, TYP-001 and TST-001. Three controls and one skill
because they share two files: a pre-commit config and a gating workflow. Three
separate skills writing those in turn would each rewrite what the last one
wrote, which is why gates are grouped by the artefact they write.

**Five prerequisites, and how you know each is met.**

| Prerequisite | Why | How you know it worked |
| --- | --- | --- |
| A `stacks:` entry for every stack you are in | The linter, the type checker, their config locations, the strictness key and the editor extension all come from there. There is no default | `uv run register-check explain LNT-001` prints the control; `uv run register-check run --control LNT-001` names your stack in its message |
| Each gate's `invocation` reaches the artefact your lockfile pins | That string is what the skill writes at every locus. A bare tool name resolves from `PATH`, so the deployed gate runs whatever global is installed rather than the pinned version ([ADR 0020](adr/0020-a-locus-reaches-the-pinned-artefact.md)) | The skill stops before writing anything and says which invocation is bare |
| A CI job that installs from the lockfile before these steps | Lint, type check and tests run the tools that install placed. A lint step before the install lints against nothing | SUP-001 passing, and the three steps sitting after the install step in the same job |
| A test command the register accepts for your ecosystem | `ecosystems.<name>.test_commands` bounds the set; your repository picks the member. The skill asks rather than choosing | `uv run register-check run --control TST-001` reports the command runs and its exit code is the verdict |
| An `ecosystem:` on your stack, and an `add_dev_dependency` for the lockfile you use | The gate has to be able to create a pin that is missing. `uv add --dev` and `poetry add --group dev` are both python, so the register says which one your repository uses | The schema rejects a register whose stack names an ecosystem that does not cover every lockfile it declares — `uv run register-check schema` names the field |

**Expect exit `0` here, unlike `gate-secrets`.** All three controls verify from
files and none declares a `remote` locus, so nothing is waiting on Phase 3. A
`3` means a block declared itself partial — read which, rather than rounding up.

**Four ways an adopter who already had these controls passing can now fail
them.** Each is the check working, not a new rule:

1. **Strictness is read, not assumed.** TYP-001 carries `baseline: null`. If
   turning the strictness key on surfaces existing type errors, there is nowhere
   to record them — the skill reports the count and stops rather than weakening
   the setting it was asked to deploy.
2. **A coverage allow-list is judged by what it leaves out.** `files = [...]` in
   a type checker's config excludes everything it does not name, so a tracked
   module nothing imports is unchecked while the control claims all first-party
   source. The gate lists every such file and extends the list
   ([ADR 0019](adr/0019-exemptions-cannot-hide-tracked-files.md), applied to an
   allow-list rather than an exemption list).
3. **A suppressed step is not a gate.** Nothing the gate writes may carry
   `continue-on-error` or end in an idiom from the register's `suppression:`
   list. LNT-001 and TST-001 both verify through `no-failure-suppression`, and
   `|| true` on the lint step fails both of them at once.
4. **A wired tool your lockfile does not pin.** From register contract 13,
   LNT-001 and TYP-001 verify that the tool exists in a lockfile you commit as
   well as that every locus invokes it. A repository that lints with a globally
   installed linter — one nobody pinned, and which can differ between your
   machine and CI — now fails, naming the tool and the lockfile. The gate adds
   the dependency for you and reports every one it added by name: a tool your
   repository did not previously depend on is a change to what it builds, not
   only to how it is checked
   ([ADR 0020](adr/0020-a-locus-reaches-the-pinned-artefact.md), case C).

**Wiring by hand instead?** Stamp what you write, as § 3.1 says for the secrets
gate — and stamp **each control's own artefacts**. All three read back a stamp
naming themselves, so recording your CI steps and forgetting the editor locus
fails LNT-001 even though TST-001 passes. This repository's own six
quality-gate stamps say *adopted rather than deployed*, because the artefacts
were hand-written in Phase 0.5 before there was a gate to write them.

### 3.3 — `gate-supply-chain`, and the locus that was never checked

`/gate-supply-chain` wires SUP-001 (*dependencies resolve from a committed
lockfile*), SUP-002 (*dependency updates are proposed automatically*) and
SUP-003 (*third-party CI actions are pinned to a commit SHA*). Three controls
and one skill because they are one property split three ways — what a build
resolves, how it stays current, and what it is allowed to fetch — and because
SUP-001's install step has to sit **above** every other gate's steps in the
gating workflow. Every one of them runs the tools that install places.

**Four prerequisites, and how you know each is met.**

| Prerequisite | Why | How you know it worked |
| --- | --- | --- |
| A tracked lockfile for every ecosystem you are in | The gate stops rather than generating one. A lockfile a skill produces pins a resolution nobody reviewed | `uv run register-check run --control SUP-001` names the ecosystem and the lockfile it expected |
| A `frozen_install_command` for the lockfile you use | `uv sync --frozen` and `poetry install --sync` are both python. Which is right is a fact about your repository | The schema rejects a register whose command matches none of its own ecosystem's `frozen_install` patterns — so a gate cannot write a step the checker then refuses |
| A `tools.register-check` entry with an `invocation` | SUP-003's pre-commit gate is the checker itself, and a locus running a bare name resolves from `PATH` — what answered would be auditing your repository ([ADR 0020](adr/0020-a-locus-reaches-the-pinned-artefact.md)) | The gate stops before writing anything and says the invocation is missing |
| A gating workflow — one that runs on `push` or `pull_request` | A workflow only a human can trigger is not the ci locus | GOV-001 reports every blocking control reachable from a step that can fail |

**Expect exit `0`.** None of these three declares a `remote` locus, so nothing
is waiting on Phase 3. A `3` means a block declared itself partial.

**Two ways a repository that already had SUP-003 passing can now fail it.**

1. **A declared locus with nothing at it.** Until register contract 14, SUP-003
   verified neither of the two loci it declares. `actions-pinned-to-sha` reads
   the *property* — every `uses:` is a commit SHA — out of the files on disk,
   which is a different claim from *something enforces this before a commit
   lands and before a merge does*. This repository reported SUP-003 PASS with no
   pre-commit hook for it of any kind. If yours does too, the gate writes one;
   the property and the loci now fail independently, and the report says which.
2. **Running the checker where you meant to audit with it.** A hook or step
   invoking `uv run register-check schema`, `meta`, `assert` or `explain`
   reaches no control at all. This repository's own pre-commit config ran
   `uv run register-check schema` and would otherwise have been credited with
   a SUP-003 gate that could never have failed it.

**The config is not the bot.** A `.github/dependabot.yml` is inert until
Dependabot is enabled on the repository, and a `renovate.json` is inert until
the Renovate app is installed and its onboarding pull request is left open
rather than closed — both platform acts, both in § 1.1. The gate writes the
file and says which act you now owe it. **A pin nothing updates rots at a known
version**, which is a different failure from an unpinned one and not a better
one, so SUP-002 exists to keep SUP-003's SHAs and DEV-001's digests current
rather than merely fixed.

**Wiring by hand instead?** Stamp what you write, and stamp **each control's
own artefacts**. All three read back a stamp naming themselves, so recording
your install step and forgetting `dependabot.yml` fails SUP-002 while the other
two pass. This repository's own four supply-chain stamps say *adopted rather
than deployed*, because the artefacts were hand-written in Phase 0.5 before
there was a gate to write them.

### 3.4 — `gate-build`, and what it pins rather than chooses

`/gate-build` wires BLD-001 (*every container image stage ends as a non-root
user*) and DEV-001 (*devcontainer features are version-pinned*). Two controls
and one skill because they read the same file: BLD-001 wants a user, DEV-001
wants two pins, and both are keys in `devcontainer.json`.

**It pins what it finds; it does not choose.** Deciding *which* image and which
features your repository uses is the template's, or your own where the template
does not fit. This gate insists that whichever were chosen are pinned. Inventing an image or a user here
produces a container that does not start, which is a worse failure than the one
being fixed.

**Three prerequisites, and how you know each is met.**

| Prerequisite | Why | How you know it worked |
| --- | --- | --- |
| A base image that defines a non-root user | The gate writes the user the image provides, not one it invents | `docker run --rm <image> id -un` names a user; `uv run register-check run --control BLD-001` then reports it |
| A `tools.register-check` entry with an `invocation` | Both controls' pre-commit gate is the checker, and a locus running a bare name resolves from `PATH` — what answered would be auditing your repository ([ADR 0020](adr/0020-a-locus-reaches-the-pinned-artefact.md)) | The gate stops before writing anything and says the invocation is missing |
| A `tools.hadolint` entry, **if you have a Dockerfile** | BLD-001's container half runs the linter. An absent linter is `UNCLASSIFIED — cannot verify`, not a pass ([ADR 0016](adr/0016-exit-codes-for-unverifiable-controls.md)) | `uv run register-check run --control BLD-001` stops reporting UNCLASSIFIED for that block |

That last row is § 3.7 in miniature — *your register records your own files*.
This standard's register pins no `hadolint`, because this repository has no
Dockerfile to lint, and a `pinned_at` naming a site that does not exist is a
failure rather than a placeholder. A repository that does have one adds the
entry, naming the loci **it** installs the linter at.

**Two half-states this gate exists to catch.** Each reads as solved and is not:

1. **A lock file covering some features.** This project's own Phase 0.5 exit
   criterion was re-opened over exactly that — a lock file pinning three of four
   features.
2. **A complete lock file over a floating image tag.** The more dangerous of the
   two, for the same reason. Both halves or neither.

And one that is not a half-state at all: **a devcontainer naming neither
`containerUser` nor `remoteUser`** runs as whatever its base image uses, which
may be root today and may become root on any digest bump. Non-root by luck is
not the property BLD-001 states.

**A shared file, and who owns which part of it.** `gate-build` owns
`.devcontainer/setup.sh` and creates it when absent. It does not own what other
gates install there: `gate-secrets` writes and stamps the scanner's install
block, and `gate-supply-chain` the package manager's — exactly as four gates
write their own hooks into one `.pre-commit-config.yaml`. `gate-build` writes no
stamp of its own in that file, because neither of its controls has a locus
there, and a stamp naming a control whose locus the file is not is a claim
rather than a record.

**Wiring by hand instead?** One hook can enforce both controls — the command is
the same — but it needs **two** stamps. The read-back matches on the control
being evaluated, so a hook stamped for BLD-001 alone leaves DEV-001's pre-commit
locus unrecorded even though the same command enforces it.

### 3.5 — `gate-iac`, and the verdict that is not a pass

`/gate-iac` wires IAC-001 (*infrastructure code is statically analysed before
apply*). It applies only if you have `*.tf` files: the predicate is evaluated
against files and never self-declared, so a repository without them skips the
control and there is nothing to deploy.

**One hook runs both analysers.** IAC-001's verify blocks are
`checkov --directory . --compact --quiet` and `tflint --recursive`, and the hook
runs the *control* — `uv run register-check run --control IAC-001` executes both
through the same path the audit uses. Two hooks each invoking one analyser would
be two statements of what "analysed" means, free to drift from each other and
from the register.

**Two prerequisites, and how you know each is met.**

| Prerequisite | Why | How you know it worked |
| --- | --- | --- |
| A `tools.checkov` and `tools.tflint` entry in your register | Without them the analysers are unpinned, and an absent analyser is `UNCLASSIFIED — cannot verify`, not a pass | `uv run register-check run --control IAC-001` stops reporting UNCLASSIFIED for those blocks |
| A `tools.register-check` entry with an `invocation` | The pre-commit gate is the checker, and a locus running a bare name resolves from `PATH` ([ADR 0020](adr/0020-a-locus-reaches-the-pinned-artefact.md)) | The gate stops before writing anything and says the invocation is missing |

**Expect `UNCLASSIFIED` on the first run, and do not treat it as a pass.** This
standard's register pins neither analyser, because this repository has no `*.tf`
to analyse. The gate will **not** make the report green by installing an
unpinned tool — that leaves the version unrecorded, which is exactly the
condition `tool_versions_match_register` exists to fail.

**Exit `1` has two causes and they are not the same.** A failing wiring or stamp
block is a failed deployment. A failing `checkov` or `tflint` block is a
*successful* deployment finding real problems in your Terraform — the gate
working on its first run. Conflating them is how a working gate gets rolled
back, so the skill reports which and quotes the block.

**What it leaves alone.** `terraform validate` checks syntax and provider
schema, which neither analyser does — a different check, not a predecessor. A
second analyser such as `tfsec` is not a violation, but two analysers means two
suppression files and only one of them is a place this standard checks
([ADR 0019](adr/0019-exemptions-cannot-hide-tracked-files.md)); the skill shows
what each is configured to do and asks.

**A suppressed step is not a locus.** From register contract 16, a CI step
carrying `continue-on-error: true` does not satisfy any control's ci locus. The
tool runs, the job succeeds whatever it reports, and the merge is not gated on
it. The same tightening applies to every gate, not only this one.

### 3.6 — `gate-repo`, the one that changes something outside your repository

`/gate-repo` wires CI-001 (*the default branch cannot be written to without a
passing check*). It is the only gate whose effect is not a file you review
before it takes effect: it calls the GitHub API, and **the ruleset is in force
the moment the call returns**, for everyone with access.

So it confirms explicitly before acting, on every run, regardless of any plan
already approved — including one approved in `register-adopt`. That plan covers
what will be written to files; this call is not a file. A re-run that would
change nothing still asks, because a call whose effect is invisible until it is
wrong is not one to make silently.

**Three calls, three questions.** Creating a ruleset, replacing one that already
exists, and removing classic branch protection are asked separately and in their
own words, because two of them can *reduce* what protects your branch: a `PUT`
replaces a ruleset entire, so anything the live one carries that your record
does not — a bypass list, an extra rule — is dropped by the call, and a `DELETE`
takes the classic rule away. An answer to one is not an answer to another. If
you are re-running the gate over an existing ruleset, the question you are asked
names the difference the call will apply, **including when there is none**.

**Two prerequisites, and how you know each is met.**

| Prerequisite | Why | How you know it worked |
| --- | --- | --- |
| A token with `administration: write` on the repository | Writing a ruleset needs it, and it is granted by a human with admin (§ 1) | `gh api repos/<owner>/<name>/rulesets` returns rather than 403 |
| Agreement that the default branch stops accepting direct pushes | It applies to **everyone**, including administrators, unless a bypass is configured | The gate states the blast radius before asking, and names who it affects |

The gate stops **before writing anything** when the token lacks the permission.
A skill that writes the record and cannot apply it leaves a repository looking
protected in a diff and unprotected in fact.

**A recorded ruleset is not a protected branch.** `gate-repo` writes
`.github/rulesets/default-branch.json` and then applies it. GitHub does not read
a path in your repository to decide what protects your default branch; only the
API call does. The file is a record, and the checker verifies it as one:
`ruleset_recorded_matches_register` says *intent only* in its own message.

**Two blocks, two different questions.** The file block verifies that you
*record* the ruleset the register requires. The remote block asks GitHub which
rules are actually **in force** on your default branch, and only that one can
say the branch is protected. Neither stands in for the other, and the messages
say which is which. A ruleset you recorded but never applied passes the first
and fails the second — which is the whole reason the second exists.

**Name the checks you require, in your own register.** CI-001's
`required_checks:` is a list of **job ids** from workflows that run on `push` or
`pull_request` — `register-check` and `lint-md` in this repository, whatever
yours are called in yours. This is § 3.7 again: keeping ours would give you a
ruleset waiting for checks your CI never reports, which blocks every merge
rather than gating one.

The checker holds the list to your workflows, so you cannot get it wrong
quietly. A name no gating job produces fails, and so does a name whose job
carries `continue-on-error` — a required check that always succeeds requires
nothing.

**Five things the checker rejects in a recorded ruleset**, each of which GitHub
itself would accept, or in one case would not:

1. **`enforcement: evaluate`.** It reports what would have happened and blocks
   nothing — a control declared and unreachable.
2. **A ruleset targeting a branch by name.** `~DEFAULT_BRANCH` follows the
   default; `refs/heads/main` stops protecting it the day your default moves,
   silently.
3. **A ruleset git does not track.** Nobody can review it, and the remote block
   cannot be reached without credentials either — so nothing at all about the
   control would have been verified.
4. **A `required_status_checks` rule naming no check.** It requires nothing, so
   a pull request merges with CI red while the control reports satisfied. This
   is what `gate-repo` itself wrote until register contract 19.
5. **A rule missing the `parameters` GitHub's schema requires** — on
   `pull_request` and `required_status_checks` — or supplying them where the
   schema accepts none, on `non_fast_forward` and `deletion`. This is the one
   GitHub would *not* accept: the apply call returns 422, and a record that
   cannot be applied is not a record of what protects your branch.

**Already have branch protection?** Say so and let the gate transcribe it. This
repository's own record was adopted rather than deployed: the ruleset was
created by hand in Phase 0.5, and the file is what the API returns today,
including a `deletion` rule the register does not ask for. An extra rule adds a
restriction; a record that disagrees with what is enforced is worse than one
carrying more than the register requires.

**Classic branch protection and a ruleset both apply**, and the union of their
requirements is enforced. Removing the classic rule is a real reduction until
the ruleset is confirmed active, so the gate confirms first and asks second.

### 3.7 — Your register records your own files

Two things in `controls.yaml` describe **the repository being checked**, not this
one, and are the first edits an adopter makes to their copy:

| What | Where | Why it is yours and not ours |
| --- | --- | --- |
| Every file that repeats a pinned tool version | `tools.<tool>.pinned_at` | `tool_versions_match_register` compares exactly these paths. A path listed here that does not exist is a failure, and so is one that exists and holds no pin — which is how a renamed workflow is caught rather than silently dropped from comparison |
| Which package ecosystems you are in, and what a frozen install looks like in them | `ecosystems:` | Detected from your manifests. If your CI installs with an idiom the register has not heard of, add it there rather than working around it in the checker |
| Where a literal-pinned tool's release comes from | `tools.<tool>.release_repo` | A fork or an internal mirror is a reasonable thing to differ on. A gate skill downloads from exactly this repository, so a wrong value fails at the checksum rather than installing something else |
| Which interpreter your gates run on, and the file that says so | `tools.<tool>.toolchain` | `.python-version` is uv's spelling; `.nvmrc`, `.tool-versions` and `.go-version` are other toolchain managers' spellings of the same thing. The register names the file, the file names the version, and SUP-001 fails if git does not track it |

**Pin the interpreter, and do not mistake a floor for a pin.** This is the
fourth row, and it is the one an adopter is most likely to think is already
done. A support constraint — `requires-python`, an `engines` field, a `go`
directive — declares which versions the *package* works on. It selects nothing:
a resolver satisfies it with whatever the machine already has, so two loci
answer differently without either being misconfigured. This repository ran its
own gates on 3.13 locally and 3.14 in CI for exactly that reason, with nothing
reporting it, until [ADR 0027](adr/0027-the-interpreter-is-a-pinned-tool.md).

The gap, in your own repository: the first line is what a local gate runs on,
the second what CI ran on. If they disagree, nothing is wrong with your
configuration — there is no configuration, which is the problem.

```bash
uv run python -V
gh run view --log | grep -iE 'Using CPython|platform linux'
```

Commit the toolchain file, keep the support floor honest, and let the linter
derive its target from the floor rather than restating it — ruff reads
`requires-python` when `target-version` is absent, and a written-out
`target-version` is a third copy free to drift from both.

Get the first one wrong and SUP-001 tells you so by name — *"recorded as pinned
at X, which does not exist"*. That message is the check working: this repository
carried four of its own filenames inside `register-check` until contract 8, so an
adopter was told their tools were "pinned at no known locus" against a list of
paths they had never had ([§ H2](09-phase-1.5-review.md#h--what-a-review-of-the-closed-phase-found)).

Files this repository's gates deploy carry a provenance stamp naming the control,
the deploying skill and the register contract; see
[`00-concepts.md`](00-concepts.md) § The provenance stamp.

## 4 — Run the checker

If `register-check` is not there, it is not installed — § 2.3 is the step that
puts it there, and it is a step rather than an assumption.

```bash
uv run register-check
uv run register-check run --tier 1
uv run register-check run --control SEC-001
uv run register-check explain SEC-001
uv run register-check schema
uv run register-check --repo ../other
uv run register-check --repo ../other --register ./controls.yaml
```

| Line | What it runs |
| --- | --- |
| `register-check` | The whole register |
| `run --tier 1` | Tier 1 only — note the `run` |
| `run --control SEC-001` | One control — what a gate verifies through |
| `explain SEC-001` | Why a control exists, and what it checks |
| `schema` | Validate the register itself |
| `--repo ../other` | `--repo` goes before the subcommand |
| `--repo ../other --register ./controls.yaml` | A repository with no register of its own — every adopter, until they commit one. Without `--register`, the checker looks for `../other/controls.yaml` and reports that it cannot read it |

### 4.1 — Remote checks: what they need, and what they refuse to guess

Three Tier-1 controls verify **platform state** rather than files, and no file
can answer them. CI-001 asks which rules GitHub has in force on your default
branch; SEC-001 asks whether secret scanning push protection is enabled; SEC-003
asks when the credential CI carries expires. Everything below is
[ADR 0021](adr/0021-how-remote-verification-authenticates.md).

**Give it a token.** The checker reads `GITHUB_TOKEN`, then `GH_TOKEN`. Nothing
is read from `gh`'s configuration and no binary has to be installed. The token
is sent as a bearer header, never in a URL.

In a local shell, export a token and the remote blocks answer:

```bash
export GITHUB_TOKEN=$(gh auth token)
uv run register-check
```

**In CI you must pass it explicitly.** GitHub Actions does *not* put
`GITHUB_TOKEN` in a step's environment — it is available as `${{ github.token }}`
and a workflow has to hand it over. A conformance step without this reports
`SKIPPED (no credentials)` on a runner that had a perfectly good token
available:

```yaml
      - name: Conformance
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: uv run register-check
```

**The scopes are not the same for each control**, and this is the part that
surprises people:

| Control | Reads | Needs |
| --- | --- | --- |
| CI-001 | `GET /repos/{owner}/{repo}/rules/branches/{branch}` | Read access to the repository. The default Actions `GITHUB_TOKEN` is enough on a public repository |
| SEC-001 | `security_and_analysis` on `GET /repos/{owner}/{repo}` | **Repository administration read.** GitHub omits the whole object for a caller without it |
| `gate-repo`, to *create* the ruleset | `POST /repos/{owner}/{repo}/rulesets` | `administration: write`, granted by a human with admin (§ 3.6) |
| SEC-003 | The `github-authentication-token-expiration` header on `GET /rate_limit` | Nothing beyond a valid token — the question is about the credential, not about the repository. **Answers only inside a GitHub Actions job**: the token in your shell is a different credential, so anywhere else it is `UNCLASSIFIED` |
| SEC-003 | The `X-OAuth-Scopes` header on the same call | Nothing beyond a valid token. Its presence means a **classic** token, which fails: a classic token grants its readers every repository its owner can reach |
| GOV-001 | `GET /repos/{owner}/{repo}/rules/branches/{branch}` | Read access to the repository. From register contract 26 the meta-control reads which checks GitHub enforces, so the chain from a control to a blocked merge is read end to end (§ 4.2) |
| SUP-004 | The release's published checksum manifest, e.g. `.../releases/download/{tag}/sha256.sum` | **Nothing.** It is the one remote check that presents no credential, because a release manifest is public — and it must not, or a run without a token would report `SKIPPED` over a question it could have answered. What it needs instead is a *network*: unreachable is `UNCLASSIFIED`, which `--require-complete` promotes to a failure ([ADR 0041](adr/0041-a-pinned-digest-is-checked-against-what-was-published.md)) |

The middle row is the one to plan for. A token that cannot see
`security_and_analysis` gets an answer with the setting simply absent — not
`disabled`. The checker reports `UNCLASSIFIED` for that, and **will not** read
the absence as push protection being off: doing so would report a violation on a
repository where the control holds, produced entirely by not having looked.

**Which repository it asks about.** Your `origin` remote, parsed from
`git remote get-url origin`. Nothing to configure, and nothing to keep in step
when a repository is renamed or transferred. Override it when the checkout is
not the repository you mean — a fork, a mirror, or auditing one repository from
another:

```bash
uv run register-check --github-repo my-org/the-real-one run --control CI-001
```

The flag goes **before** the subcommand, like `--repo` and `--require-complete`.

**What each refusal means.** All four of these deny the run a `0` exit, so none
can be mistaken for a pass — but they ask different things of you:

| The report says | What happened | What to do |
| --- | --- | --- |
| `SKIPPED (no credentials)` | No token in the environment | Supply one |
| `UNCLASSIFIED`, *token was rejected* | 401 — invalid or expired | Fix the token |
| `UNCLASSIFIED`, *answered 403* | Either the token lacks administration access, or the plan does not sell the feature — a private repository has neither rulesets nor push protection below a paid tier | Read GitHub's own sentence and the permission it names, both of which the report quotes. If your token holds the accepted permission, the plan is refusing. *Upgrade to GitHub Pro* is a plan limit, recorded in `deployment-decisions.yaml` ([ADR 0047](adr/0047-a-plan-limit-is-recorded-not-tolerated.md), and `START-HERE.md` § If your plan has no rulesets); anything else is the scope in the table above |
| `UNCLASSIFIED`, *not visible to this token* | 404 — the repository does not exist, or the token cannot see it | Check the slug and the token's access |
| `UNCLASSIFIED`, *says nothing about* | The answer came back without the setting | Use a token with administration read |
| `FAIL` | GitHub answered, and the branch is not protected as the register requires | Fix the platform state — this one **is** about your repository |

The last row is the mirror of all the others, and it is worth stating plainly: an
effective-rules response listing **no rules** is an answer, not a refusal. It
means nothing is protecting your default branch, and it fails.

Read the exit code, not just the report
([ADR 0016](adr/0016-exit-codes-for-unverifiable-controls.md)):

| Code | Meaning |
| --- | --- |
| `0` | Every applicable control was verified and none failed |
| `1` | A verified violation |
| `3` | No violation found, but something could not be verified |
| — | `--require-complete` promotes `3` to `1` |

**`3` is the code that matters.** It is the difference between "clean" and
"nothing looked". A run with no credentials for the remote checks exits `3`, and
treating that as success is the mistake the code exists to stop.

Verdicts to read carefully:

- `SKIPPED (predicate)` — the control does not apply to this repository. A
  legitimate pass.
- `SKIPPED (no credentials)` — no token was in the environment, so no remote
  question was asked. **Not** a pass.
- `UNCLASSIFIED` — something was asked and did not answer: an absent tool, or a
  token that was rejected, lacked the scope, or could not see the setting. Not a
  failure, and not a pass. It is deliberately distinct from the row above,
  because one needs a token supplied and the other needs one fixed.

### 4.2 — Is your conformance run a *required* check?

A control is only enforced if a merge waits for it, and that is a **chain of
four links** — none of which is in the same place as the others:

1. Your register names a control `blocking`, with a `ci` locus.
2. A job in a workflow that runs on `push` or `pull_request` runs the tool, and
   does not suppress its own failure.
3. That job's **id** is in your ruleset's `required_status_checks`.
4. The ruleset is applied on the platform, targeting the default branch, with
   `enforcement: active`.

Break any one and the control is *declared and unreachable* — the failure this
standard calls theme **T-3**. The uncomfortable part is that three of the four
breaks leave a repository looking conformant: the workflow exists, the job runs,
the file is committed, and the report is green.

**GOV-001 reads the whole chain** from register contract 26. It has two halves,
and they need different things from you:

| Half | Reads | Needs |
| --- | --- | --- |
| The file half | Your register, your workflows | Nothing. Links 1 and 2 |
| The platform half | `GET /repos/{owner}/{repo}/rules/branches/{branch}` | A token. Links 3 and 4 |

Without a token it reports `SKIPPED (no credentials)` **and says which half it
did verify** — a bare skip would throw away the file-level chain it read. That
is not a pass, and `--require-complete` (§ 4.3) turns it into a failed check.

**Three ways the chain breaks, and how each reads:**

| What is wrong | What the report says | What to do |
| --- | --- | --- |
| The job runs, but no ruleset requires it | GOV-001 `FAIL`, naming the check your register requires and the platform does not enforce | Add the job id to `required_checks:` in your register and re-run `/gate-repo` |
| The ruleset requires it, but nothing produces that check | CI-001 `FAIL` — *produced by no job in a gating workflow* | The register and the workflows disagree. Only you know which of the two is right; GitHub waits forever for a check nothing reports, so this blocks **every** merge rather than gating one |
| The ruleset exists in your repository and was never applied | The file block passes — *intent only* — and the remote block fails or is skipped | A recorded ruleset protects nothing. Apply it (§ 3.6) |

```bash
# The whole chain, in one verdict.
uv run register-check meta GOV-001

# What GitHub actually enforces on your default branch, in its own words.
gh api "repos/{owner}/{repo}/rules/branches/$default" \
  --jq '[.[] | select(.type == "required_status_checks")
        | .parameters.required_status_checks[].context]'
```

**And the observation no report replaces.** Open a pull request whose required
check fails, and watch the merge button refuse. This is § 1's rule again, one
level up: *a ruleset nobody has seen refuse anything is not known to work.* Four
green links and a merge that goes through anyway is the one outcome none of the
checks above can rule out, because every one of them is reading a description of
the platform rather than trying it.

### 4.3 — Giving CI a credential, and failing the run when it cannot verify

Two things go together, and doing either alone makes the other worse.

**`--require-complete` turns "could not verify" into a failed check.** Without
it, a run that answered nothing prints that it answered nothing and passes —
which is the state most repositories are in without noticing, because exit `3`
is reported and nothing reads it.

```yaml
      - name: Conformance
        run: uv run register-check --require-complete
```

**That snippet is the shape, not the whole answer.** Where the flag can be
passed depends on where the credential can be read, and under the arrangement
below a pull request cannot read it at all — see § The strict run is the one on
your default branch. The decision that arrangement rests on is recorded as owed
rather than taken: it narrows *a run that cannot verify fails* to the default
branch, which is a weakening of what
[ADR 0016](adr/0016-exit-codes-for-unverifiable-controls.md) states, and this
guide does not get to make that decision on its own.

**So the token has to come first.** Turn on `--require-complete` while CI has no
credential and every run fails on a control that holds — and a check that fails
for reasons nobody can act on gets ignored, which is worse than the tolerance it
replaced. Order: token, confirm the remote blocks answer, then the flag.

#### The credential, and where it lives

A fine-grained token, scoped to the **one repository**, with
`Administration: read` and nothing else. That one permission is what the Actions
`GITHUB_TOKEN` does not carry and what SEC-001's remote block needs — without
it, GitHub omits `security_and_analysis` entirely and the block reports
`UNCLASSIFIED` over a repository where push protection is on.

**Put it behind a deployment environment**, not in a plain repository secret.
[ADR 0022](adr/0022-a-platform-token-ci-carries.md) sets out why, and the short
form is that a repository secret is readable by any workflow run that reaches
it, including one a pull request added a trigger for. An environment carries a
**branch policy** — limit it to your default branch — and that policy lives in
repository settings rather than in the workflow file, so it is a guard the pull
request cannot edit. A guard written in the file being changed is not a guard.

**And that branch policy is why a pull request can never carry this credential.**
A `pull_request` run's ref is `refs/pull/N/merge`, which no policy naming your
default branch can match. GitHub does not quietly withhold the secret — it
refuses the job outright, in about a second, before any step runs:

```text
Branch "refs/pull/5/merge" is not allowed to deploy to conformance
due to environment protection rules.
```

Loosening the policy until that ref matches is not the answer: a fork's pull
request produces the same ref in *your* repository, so the pattern that admits
your contributors admits everyone. That is the exfiltration path Option 3 exists
to close.

**So take the environment only on the default branch**, and key it on the branch
rather than on the event — pushing a *branch* is a `push` too, and asks for the
environment just as a pull request does:

```yaml
  register-check:
    runs-on: ubuntu-latest
    environment: >-
      ${{ github.ref == format('refs/heads/{0}',
          github.event.repository.default_branch) && 'conformance' || '' }}
```

An empty string means no environment. Read the branch name from the repository
rather than typing it, or renaming your default branch silently moves which run
is the strict one.

#### The strict run is the one on your default branch

This is the consequence, and it is a real narrowing rather than a detail.

**Exit `3` is non-zero, so a bare `run:` fails on it whether or not you pass
`--require-complete`.** A pull request has no platform credential — by the
design above, not by oversight — so SEC-001's and SEC-003's remote blocks cannot
answer, the run exits `3`, and the step fails. Every pull request, for a reason
no contributor can act on, which is the failure this whole section warns about.

So a pull request runs the same audit with the job token and tolerates exit `3`,
**and only `3`**. A verified violation still fails it:

```yaml
  register-check:
    runs-on: ubuntu-latest
    # Repeated from above on purpose: the line that reaches the secret and the
    # line that gates it belong in front of the same reader.
    environment: >-
      ${{ github.ref == format('refs/heads/{0}',
          github.event.repository.default_branch) && 'conformance' || '' }}
    steps:
      - name: Conformance
        env:
          GITHUB_TOKEN: ${{ secrets.PLATFORM_READ_TOKEN || github.token }}
          REF: ${{ github.ref }}
          DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}
        run: |
          if [ "$REF" = "refs/heads/$DEFAULT_BRANCH" ]; then
            uv run register-check --require-complete
          else
            uv run register-check && status=0 || status=$?
            if [ "$status" -ne 0 ] && [ "$status" -ne 3 ]; then
              exit "$status"
            fi
          fi
```

**What this costs you, stated rather than buried.** A pull request is gated by
the audit that *can* run, and the strict one lands after the merge. So a change
that leaves a control unverifiable can be merged, and your default branch goes
red immediately afterwards rather than the pull request going red before. That
is a consequence of holding the credential where a pull request cannot reach it,
not a preference — and if it is not a trade you want, the alternative is not
loosening the branch policy but deciding that your repository can hold the token
as an ordinary repository secret, which
[ADR 0022](adr/0022-a-platform-token-ci-carries.md) permits only where every
account that could read it already holds admin.

A fork's pull request needs no separate treatment here: it takes the same path
as any other pull request, for the same reason, which is why the fallback to
`github.token` is written into the `env:` block above.

**Test both branches**, in a test that runs the step's own script rather than a
copy of it. A carve-out nobody exercises is one that quietly becomes general —
which is exactly what happened to the tolerance it replaces.

#### Name it in your register before you create it

SEC-003 is an allow-list (§ 3.1), so a secret your workflow reaches and your
register does not name **fails** — which is the intended order. The register has
to be able to see the credential before the credential exists.

```yaml
platform_credentials:
  - name: PLATFORM_READ_TOKEN
    triggers: [push, pull_request]    # not `any` — a standing credential
    max_lifetime_hours: 2184
```

**`max_lifetime_hours` is a permission, not a measurement.** It is the longest
life your register allows *any* standing credential, and the remote block
compares the expiry GitHub reports against the largest number any entry permits
— no API response says which credential a run is carrying, so it cannot be
per-token.

Add a day to your policy when you write it in hours. This repository's ninety-day
policy is recorded as **2184**, not 2160, because the block failed on its first
live run by forty-four minutes: an expiry is a timestamp, and a token issued for
"90 days" still had 2160.73 hours left when the run read it. That extra day is
what a policy costs to state in hours — not slack granted to make a report
green.

#### If your repository takes fork pull requests, or lets Dependabot open them

Two run shapes receive no repository secret and no environment secret: a pull
request **from a fork**, and anything **Dependabot** opens — GitHub keeps
Dependabot's secrets in a store of its own and hands a `pull_request` run none
of the Actions ones. SEC-001's remote block cannot answer in either, and with
`--require-complete` the run fails a contributor, or a dependency update, for a
credential you deliberately did not give them. Tolerate exit `3` on that path,
**and only `3`**:

```yaml
  register-check:
    runs-on: ubuntu-latest
    environment: conformance
    steps:
      - name: Conformance
        env:
          GITHUB_TOKEN: ${{ secrets.PLATFORM_READ_TOKEN || github.token }}
          # Read into the environment rather than interpolated into the script:
          # an expression expanded into shell is a shape worth not having.
          NO_REPOSITORY_SECRET: ${{ github.event.pull_request.head.repo.fork || github.event.pull_request.user.login == 'dependabot[bot]' }}
        run: |
          if [ "$NO_REPOSITORY_SECRET" = "true" ]; then
            uv run register-check && status=0 || status=$?
            if [ "$status" -ne 0 ] && [ "$status" -ne 3 ]; then
              exit "$status"
            fi
          else
            uv run register-check --require-complete
          fi
```

A verified violation still fails either run, and the incompleteness is still
printed. **Test both branches**, in a test that runs the step's own script
rather than a copy of it: a carve-out nobody exercises is one that quietly
becomes general, which is exactly what happened to the tolerance it replaces.
If your repository takes neither fork pull requests nor Dependabot ones, do not
write this — an unused branch is a tolerance waiting to be widened.

**Name the condition, not one of its instances.** This repository wrote
`FROM_A_FORK` and had to widen it on 2026-09-07 when a Dependabot bump sat
unmergeable on precisely the verdict the fork branch exists to tolerate. And key
it on the pull request rather than on the secret: `if the token is empty` reads
identically on the happy path and lets a revoked or misspelled secret silently
downgrade every run to the tolerant branch.

The alternative — putting the token in Dependabot's own secret store — makes
those runs complete rather than tolerated, and is the wrong trade here: a
standing credential readable by a run that checks out a bot's dependency change
is a wider blast radius than the one control it settles.

#### What none of this checks

No API lets a fine-grained token enumerate its own permissions. *Scoped to this
repository, `Administration: read` only* stays a human act you record when you
issue it. SEC-003 reads the **instrument** — `X-OAuth-Scopes` present means a
classic token, and that fails — and the **expiry**, and neither is a check that
your token is minimal. Do not read a green SEC-003 as one.

### 4.4 — Which gates are current, and which are owed a re-run

A conformance run tells you whether a control **holds**. It does not tell you
whether the artefacts satisfying it are what the gate would write today. Those
are different questions, and the second has its own command:

```bash
uv run register-check deployments
```

Both this and a conformance run take `--format json` before the command
(`uv run register-check --format json deployments`) to print the same report as
data, with the same exit code, for a tool that keeps it
([ADR 0056](adr/0056-the-checker-has-a-machine-readable-report.md)).

It reads the plugin's `.claude-plugin/deploys.json` — which gate writes what, at
which **deployment contract** — and the `ee-control:` stamps in your repository,
and it gives each gate one of six states:

| State | What it means | What you owe |
| --- | --- | --- |
| `NOT APPLICABLE` | no control this gate carries applies to your repository | nothing — a predicate skip is not a gap |
| `NEVER DEPLOYED` | no stamp names this gate | run the gate |
| `UNRECORDED` | deployed before the stamp carried a `gate-contract` | re-run the gate; whether it is current cannot be known |
| `STALE` | the gate's stamps are behind the installed contract | re-run the gate |
| `CURRENT` | stamped at the installed contract | nothing |
| `AHEAD` | a stamp claims a contract the installed gate has not reached | investigate — that is a defect, not staleness |

**A gate's version is not in that list.** The plugin's version moves for
documentation fixes and trigger-phrase releases, and all eight skills share it,
so nothing here reads it. What moves is the per-gate `contractVersion`, and it
moves only when what that gate writes changes — which is the whole reason you
can leave this command in a routine without it becoming noise
([ADR 0038](adr/0038-the-stamp-records-the-deployment-contract.md)).

**Nothing here fails a build.** The command exits `0` over any number of stale
or undeployed gates: staleness is *reported, never enforced*, and a re-run is a
recommendation you accept or decline. It exits non-zero only for the `AHEAD`
defect — and for a **stale record**, described next.

**Declining a release is an outcome, and it has to be written down.** A skill
you did not deploy is behind for one of two reasons: nobody got to it, or taking
it would revert something your register holds. Those are a chore and a decision,
and a report that shows them the same way trains everyone to ignore both. Record
the second in **`deployment-decisions.yaml`**, at your repository root beside
`controls.yaml`:

```yaml
declined:
  - skill: lint-md
    version: "1.0.7"
    reason: >
      It writes an invocation that resolves from PATH rather than from the
      artefact the lockfile pins, and an exemption that hides a tracked file.
    adr: docs/adr/00NN-....md
    review_by: 2026-11-27
```

It is **not** part of your register. A declination is your repository's posture,
and the register is what everyone installs
([ADR 0022](adr/0022-a-platform-token-ci-carries.md) requirement 6).

Two rules make it a record rather than a permanent opt-out, and the command
enforces both:

- **`version` covers the release it names and no later one.** Declining 1.0.7
  does not decline 1.0.8 — a new release re-opens the question, which is the
  whole point. The command checks this against the release you have
  **installed**, read from Claude Code's own plugin inventory
  (`plugins/installed_plugins.json` under `$CLAUDE_CONFIG_DIR`, default
  `~/.claude`), so updating a skill you have declined **fails** the command
  until you renew the entry against the new release or delete it
  ([ADR 0043](adr/0043-a-declination-is-reconciled-against-the-installed-skill.md)).
- **`review_by` expires it.** An entry past its date **fails** the command, the
  way GOV-003 fails a control past its review date. A declination nobody
  revisits is a permanent exemption wearing a reason.

Two more failures, both about the record rather than about a deployment: an
entry for a version you have **already deployed** (the decision no longer
applies), and one naming a skill **nothing in your repository stamps**. And a
file that will not parse exits `2` rather than reading as no declinations —
which would report every declined deployment as a chore nobody got to, in a
report that looked entirely ordinary.

**Where the inventory cannot be read, the command says so instead of passing.**
CI has no plugins installed, so a scheduled or workflow run will report your
declinations as *not reconciled against an installed release* and name the
reason, rather than reporting them as still covered — a verdict produced by not
having looked is not a verdict. Expect this command's exit code to differ
between your machine and CI for that reason alone; the expiry rule still bounds
every entry in both. If your plugin is installed somewhere the command cannot guess, pass
`--plugin <plugin root>` or set `CLAUDE_PLUGIN_ROOT`.

**How you know it worked:** run it before deploying anything and every gate
reads `NEVER DEPLOYED` or `NOT APPLICABLE`; run it after `/register-adopt` and
every gate you deployed reads `CURRENT`. If one still reads `NEVER DEPLOYED`
after its gate ran, the gate wrote an artefact and did not stamp it — report
that, do not add the stamp by hand.

### 4.5 — The sweep: a report nobody has to ask for

Everything in § 4.4 answers when you run it. **Several controls can start
failing with no commit at all**: SUP-004 reads what a project published and a
release can be re-cut; GOV-003 expires on a date; SEC-001's and SEC-003's remote
blocks read platform state an administrator can change. In a quiet month the
next person to notice is whoever opens the next pull request.

Two scheduled runs close that, and they are deliberately separate.

**Add `schedule:` to your conformance workflow.** One line, no new file, and the
run that already knows how to install its tools is the run that should do it. A
schedule run has no pull request, so any fork carve-out you wrote does not apply
— which is right, because it runs on your default branch with your own secrets.

```yaml
on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: "23 5 * * 1"
```

**Then copy the sweep.** Where it is depends on how you got the plugin, the same
split § 2.0 draws for the devcontainer template:

```bash
# Installed from the marketplace in § 0.0.
cp ~/.claude/plugins/cache/ee-standard/control-register/*/templates/sweep/conformance-sweep.yml \
   .github/workflows/

# From a clone of the standard instead.
cp path/to/ee-standard/plugins/control-register/templates/sweep/conformance-sweep.yml \
   .github/workflows/
```

It runs
`register-check deployments` — the report with no other home, since conformance
already runs on every pull request — writes it to the job summary, and keeps
**one** tracking issue: opened when something is owed, edited while it persists,
closed when it clears. One issue and never one per run, or the sweep becomes the
noise it exists to prevent.

Three things about it are decisions rather than details:

- **It reports and never fixes.** Nothing re-runs a gate or opens a pull
  request. A deployment stays a reviewable change a person makes.
- **It does not fail on findings.** A red scheduled workflow is a notification
  people learn to dismiss, and staleness is *reported, never enforced*. It fails
  only when the sweep itself could not run.
- **It runs `deployments` and not the full audit.** Running the audit here would
  mean installing your scanner, your markdown linter and the rest a second time
  — a copy of your conformance workflow's setup, free to drift from it.

**Two register edits go with it.** Add the sweep's path to `tools.<uv>.pinned_at`,
because it repeats a pinned version. And if your conformance workflow reaches a
standing secret, add `schedule` to that credential's `triggers:` in
`platform_credentials:` — otherwise SEC-003 fails the moment the scheduled run
references a secret under an event the register does not permit.

**It needs `issues: write`**, and nothing more. The job token is enough; do not
hand the sweep your standing platform credential, which it has no question to
ask with.

## 5 — Checklist

Each row is done when its evidence exists, not when the step has been performed.

| # | Step | Evidence |
| --- | --- | --- |
| 0 | The checker is installed, pinned and locked | `uv run register-check --version` runs, and your lockfile names `register-check` at the tag the register pins (§ 2.3). Nothing below can be evidenced without it |
| 1 | Repository visibility or plan allows rulesets | `gh api "repos/{owner}/{repo}/rulesets"` returns a list |
| 2 | Default-branch ruleset created | `gh api "repos/{owner}/{repo}/branches/$(gh api "repos/{owner}/{repo}" --jq .default_branch)" --jq .protected` is `true`, and a direct push is refused |
| 3 | Secret scanning push protection on | `gh api "repos/{owner}/{repo}" --jq '.security_and_analysis…status'` is `enabled` |
| 4 | `.github/dependabot.yml` covers every ecosystem present | A Dependabot pull request appears |
| 5 | Renovate installed, if any version is a literal or a toolchain file | Its Dependency Dashboard lists the expected number of sites |
| 5a | The interpreter is pinned by a toolchain file, not by a support floor | `uv run register-check run --control SUP-001` passes, and the version your CI log reports is the one the file names |
| 6 | Devcontainer image digest-pinned, lock file complete, user stated | `uv run register-check` reports DEV-001 and BLD-001 passing |
| 7 | Gates wired at every locus the control declares | LNT-001, TYP-001, DOC-001, TST-001 passing |
| 7d | Both git hook types are installed, not just `pre-commit` | `test -x .git/hooks/pre-push`, and a push with a failing test is refused. No control checks this — `.git/hooks/` is untracked — so it is your evidence or nobody's (§ 3.0) |
| 7b | Quality gates wired at every locus **and** stamped | `uv run register-check run --control LNT-001 --control TYP-001 --control TST-001` exits `0` — every block ✓, nothing skipped |
| 7a | Secrets gate wired at pre-commit **and** CI, and stamped | `uv run register-check run --control SEC-001` shows both local blocks ✓; with an admin-scoped token the remote block is ✓ too and it exits `0` |
| 7e | SEC-002 is wired, not merely passing | `uv run register-check run --control SEC-002` exits `0` with its locus block ✓ — a repository with no workflow naming a cloud key passes the *property* whether or not anything enforces it (§ 3.1) |
| 7c | The branch protection you recorded is the one GitHub enforces | `uv run register-check run --control CI-001` with a token — the remote block reports the rules in effect, not the file |
| 8 | The conformance run is a required status check | `uv run register-check` with a token reports GOV-001 `PASS` — from register contract 26 it reads which checks GitHub actually enforces on your default branch, and fails one your register requires and the platform does not. Without a token it reports `SKIPPED (no credentials)` and says which half it did verify |
| 8a | A merge has actually been refused | A pull request whose required check fails cannot be merged. Four green links and a merge that goes through anyway is what no report can rule out (§ 4.2) |
| 9 | CI carries a credential the remote blocks can answer from | The conformance run's report shows SEC-001's and SEC-003's remote blocks ✓ rather than `SKIPPED` or `UNCLASSIFIED` — and the token is an environment secret behind a branch policy, not a repository secret (§ 4.3) |
| 9a | That credential is named in your register before it exists | `uv run register-check run --control SEC-003` passes rather than failing on a secret nothing names |
| 10 | The conformance step passes `--require-complete` | A run that cannot verify a control fails the check rather than printing that it could not. Turn it on **after** row 9, not before |
| 10a | The fork path, if you take fork pull requests | A test running the step's own script asserts it tolerates `3` and only `3` (§ 4.3). Do not write the branch if you do not need it |
| 11b | Conformance and deployments are both checked when nothing has changed | Your conformance workflow has a `schedule:` trigger, and a sweep run appears in Actions with a job summary. A control that expires or a release that is re-cut is found by a cron rather than by the next pull request (§ 4.5) |
| 11a | A release you decided not to take is recorded rather than remembered | `uv run register-check deployments` shows it under *Deliberately not deployed* with a live `review_by`, and exits `0`. An expired entry, one you have already deployed, or one whose skill you have since **updated** exits `1` (§ 4.4) |
| 11 | Every gate you deployed is current, and you can see which are not | `uv run register-check deployments` reports `CURRENT` for each gate you ran and `NOT APPLICABLE` or `NEVER DEPLOYED` for the rest — never `UNRECORDED` or `AHEAD` in a fresh adoption (§ 4.4) |

## When something is wrong with the standard itself

If a control cannot be satisfied for a reason that is about the control rather
than about your repository, that is a finding, not a workaround. Raise it. Do not
re-tier the control, and do not exclude your own files to make a report green.
An exemption may scope a gate to what git tracks — it may never hide a file git
is tracking, and the checker fails you if it does
([ADR 0019](adr/0019-exemptions-cannot-hide-tracked-files.md)). The repository
that authored that rule broke it once already and had to
[record the fix](04-build-plan.md).
