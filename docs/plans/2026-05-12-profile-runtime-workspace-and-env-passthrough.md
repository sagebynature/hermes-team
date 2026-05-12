# Profile Runtime Workspace and Env Passthrough Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Keep Team Nexus source mounted at `/workspace`, move profile default scratch output into ignored per-profile workspaces, and allow all active profiles to use approved runtime tool credentials in terminal subprocesses.

**Architecture:** `/workspace` remains the Team Nexus control repo because scripts, docs, dashboards, and Makefile contracts already depend on it. Add `/workspaces` as an ignored runtime mount backed by `runtime/hermes/workspaces`, set profile terminal defaults to `/workspaces/<profile>`, and keep Kanban-dispatched task cwd behavior unchanged. Add explicit `terminal.env_passthrough` to all active profiles for `GITHUB_TOKEN`, `CONTEXT7_API_KEY`, and `STITCH_API_KEY`.

**Tech Stack:** Docker Compose, native Hermes profile config YAML, Makefile, Python unittest validation.

---

## Requirements and Decisions

- Do not remove `/workspace`; it is the mounted Team Nexus repo/control plane.
- Do not make `/workspace` profile-specific; current ADR-0014 profile runtime uses shared function services and Hermes profiles.
- Add `/workspaces` for ad-hoc agent scratch files so accidental writes do not dirty the repo.
- Back `/workspaces` with `runtime/hermes/workspaces`, already ignored by top-level `.gitignore` via `runtime/`.
- Change profile `terminal.cwd` to `/workspaces/<profile>` for all active profiles: `atlas`, `forge`, `sentinel`, `scribe`, `curator`.
- Add `GITHUB_TOKEN`, `CONTEXT7_API_KEY`, and `STITCH_API_KEY` env passthrough for all active profiles: `atlas`, `forge`, `sentinel`, `scribe`, `curator`.
- Keep Kanban task-specific workspaces as-is. Dispatcher passes `cwd=workspace` and `HERMES_KANBAN_WORKSPACE`, so task workspace selection overrides profile default cwd.
- Prefer changing Compose mount source from `${PWD}` to `${TEAM_NEXUS_REPO_ROOT:-.}` or `.` as a small robustness improvement, but keep destination `/workspace`.

---

### Task 1: Add regression tests for workspace mount and profile cwd contracts

**Objective:** Make the desired runtime boundaries explicit before editing configs.

**Files:**
- Modify: `tests/test_makefile_contract.py`
- Modify: `tests/test_validate_profile_spec.py`

**Step 1: Add Compose/workspace mount contract test**

In `tests/test_makefile_contract.py`, add assertions that:

```python
def test_profile_runtime_mounts_control_repo_and_ignored_workspaces(self):
    compose = COMPOSE_FILE.read_text()

    self.assertIn(":/workspace", compose)
    self.assertIn("./runtime/hermes/workspaces:/workspaces", compose)
```

If the implementation uses `${TEAM_NEXUS_REPO_ROOT:-.}:/workspace`, assert that exact string instead of only `:/workspace`.

**Step 2: Add workspace-init contract assertion**

In the existing `test_mission_contract_and_notifier_use_profile_runtime_db` or a new test, assert:

```python
self.assertIn("runtime/hermes/workspaces", makefile)
```

**Step 3: Add profile config contract test**

In `tests/test_validate_profile_spec.py`, add:

```python
def test_active_profiles_default_to_ignored_runtime_workspaces(self):
    validator = load_validator_module()
    for profile in ["atlas", "forge", "sentinel", "scribe", "curator"]:
        config = validator.load_yaml(REPO_ROOT / "profiles" / profile / "config.yaml")
        terminal = config.get("terminal") or {}
        self.assertEqual(f"/workspaces/{profile}", terminal.get("cwd"))
```

**Step 4: Add approved credential passthrough test**

Add:

```python
def test_active_profiles_allow_approved_runtime_credentials_in_terminal_subprocesses(self):
    validator = load_validator_module()
    required = {"GITHUB_TOKEN", "CONTEXT7_API_KEY", "STITCH_API_KEY"}
    for profile in ["atlas", "forge", "sentinel", "scribe", "curator"]:
        config = validator.load_yaml(REPO_ROOT / "profiles" / profile / "config.yaml")
        terminal = config.get("terminal") or {}
        self.assertTrue(required.issubset(set(terminal.get("env_passthrough") or [])))
```

**Step 5: Run targeted tests to verify failure**

Run:

```bash
python -m unittest tests.test_makefile_contract tests.test_validate_profile_spec -v
```

Expected: FAIL because compose, Makefile, and profile configs do not yet satisfy the new contracts.

---

### Task 2: Add `/workspaces` mount to Docker Compose

**Objective:** Provide an ignored, writable container path for profile default scratch work.

**Files:**
- Modify: `docker-compose.profiles.yml`

**Step 1: Update shared profile volumes**

In `x-profile-runtime.volumes`, change the repo mount to a robust source and add workspaces:

```yaml
    - ${TEAM_NEXUS_REPO_ROOT:-.}:/workspace
    - ./runtime/hermes/workspaces:/workspaces
```

This replaces:

```yaml
    - ${PWD}:/workspace
```

**Step 2: Update admin-shell volumes**

Make the same change in `admin-shell.volumes`:

```yaml
      - ${TEAM_NEXUS_REPO_ROOT:-.}:/workspace
      - ./runtime/hermes/workspaces:/workspaces
```

**Step 3: Run Compose config validation**

Run:

```bash
make compose-config
```

Expected: compose config OK.

---

### Task 3: Teach workspace-init to create per-profile workspaces

**Objective:** Ensure `/workspaces/<profile>` exists before profiles use it as terminal cwd.

**Files:**
- Modify: `Makefile`

**Step 1: Update `workspace-init` mkdir**

Change the `mkdir -p` line to include profile workspace directories:

```make
	@mkdir -p shared/project/artifacts runtime/hermes/profiles runtime/hermes/kanban \
		runtime/hermes/workspaces $(addprefix runtime/hermes/workspaces/,$(TEAM_AGENTS))
```

**Step 2: Update chmod line**

Include the workspaces root:

```make
	@chmod 2775 shared/project/artifacts runtime/hermes runtime/hermes/kanban runtime/hermes/workspaces 2>/dev/null || true
```

Optionally chmod per-profile directories too if needed:

```make
	@chmod 2775 $(addprefix runtime/hermes/workspaces/,$(TEAM_AGENTS)) 2>/dev/null || true
```

**Step 3: Update echo text**

Change the message to:

```make
	@echo "workspace initialized: shared/project/artifacts, runtime/hermes, and runtime/hermes/workspaces"
```

**Step 4: Run workspace init**

Run:

```bash
make workspace-init
```

Expected: directories exist under `runtime/hermes/workspaces/` for every active profile.

---

### Task 4: Update active profile terminal cwd and GitHub env passthrough

**Objective:** Make default terminal writes land in ignored per-profile workspaces and expose approved runtime tool credentials to terminal subprocesses.

**Files:**
- Modify: `profiles/atlas/config.yaml`
- Modify: `profiles/forge/config.yaml`
- Modify: `profiles/sentinel/config.yaml`
- Modify: `profiles/scribe/config.yaml`
- Modify: `profiles/curator/config.yaml`

**Step 1: Update Atlas**

Set:

```yaml
terminal:
  backend: local
  modal_mode: auto
  cwd: /workspaces/atlas
  timeout: 180
  env_passthrough:
    - GITHUB_TOKEN
    - CONTEXT7_API_KEY
    - STITCH_API_KEY
```

**Step 2: Update Forge**

Set:

```yaml
terminal:
  backend: local
  cwd: /workspaces/forge
  timeout: 180
  env_passthrough:
    - GITHUB_TOKEN
    - CONTEXT7_API_KEY
    - STITCH_API_KEY
```

**Step 3: Update Sentinel**

Set:

```yaml
terminal:
  backend: local
  cwd: /workspaces/sentinel
  timeout: 180
  env_passthrough:
    - GITHUB_TOKEN
    - CONTEXT7_API_KEY
    - STITCH_API_KEY
```

**Step 4: Update Scribe**

Replace the minimal terminal block with:

```yaml
terminal:
  backend: local
  cwd: /workspaces/scribe
  timeout: 180
  env_passthrough:
    - GITHUB_TOKEN
    - CONTEXT7_API_KEY
    - STITCH_API_KEY
```

**Step 5: Update Curator**

Replace the minimal terminal block with:

```yaml
terminal:
  backend: local
  cwd: /workspaces/curator
  timeout: 180
  env_passthrough:
    - GITHUB_TOKEN
    - CONTEXT7_API_KEY
    - STITCH_API_KEY
```

**Step 6: Run targeted tests**

Run:

```bash
python -m unittest tests.test_validate_profile_spec -v
```

Expected: PASS.

---

### Task 5: Render runtime profiles and verify generated configs

**Objective:** Ensure ignored runtime profile configs match canonical profile configs.

**Files:**
- Generated/ignored: `runtime/hermes/profiles/*/config.yaml`

**Step 1: Render profiles**

Run:

```bash
make profile-render
```

Expected: generated configs under `runtime/hermes/profiles/<profile>/config.yaml` contain `/workspaces/<profile>` and all approved credential passthrough entries.

**Step 2: Verify rendered values without printing secrets**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
import yaml
for profile in ["atlas", "forge", "sentinel", "scribe", "curator"]:
    cfg = yaml.safe_load((Path("runtime/hermes/profiles") / profile / "config.yaml").read_text())
    terminal = cfg.get("terminal") or {}
    passthrough = set(terminal.get("env_passthrough") or [])
    required = {"GITHUB_TOKEN", "CONTEXT7_API_KEY", "STITCH_API_KEY"}
    print(profile, terminal.get("cwd"), required.issubset(passthrough))
PY
```

Expected output shape:

```text
atlas /workspaces/atlas True
forge /workspaces/forge True
sentinel /workspaces/sentinel True
scribe /workspaces/scribe True
curator /workspaces/curator True
```

---

### Task 6: Update docs that describe runtime mounts and workspace policy

**Objective:** Keep operator docs aligned with the new control-repo vs scratch-workspace distinction.

**Files:**
- Modify: `README.md`
- Modify: `docs/discord-kanban-operations.md`
- Optional Modify: `docs/team-nexus-operations.md`

**Step 1: Update mount tables**

Where docs show:

```text
repo root                  -> /workspace
```

add:

```text
repo root                  -> /workspace (control repo; intentional edits only)
runtime/hermes/workspaces  -> /workspaces (ignored per-profile scratch cwd)
```

**Step 2: Add policy note**

Add a short note:

```markdown
`/workspace` is the Team Nexus control repository. Profiles default their terminal cwd to `/workspaces/<profile>` so ad-hoc scratch files do not dirty the repo. Use `/workspace` explicitly for intentional Team Nexus source/docs/config edits, and use Kanban `workspace: scratch` or task-specific worktrees for delegated work.
```

**Step 3: Run documentation grep sanity check**

Run:

```bash
grep -R "repo root.*-> /workspace\|/workspaces" README.md docs/discord-kanban-operations.md docs/team-nexus-operations.md
```

Expected: docs mention both `/workspace` and `/workspaces` roles.

---

### Task 7: Full validation and runtime smoke test

**Objective:** Prove the change works in tests and in Docker without leaking token values.

**Files:**
- No source edits expected.

**Step 1: Run repo validation**

Run:

```bash
make validate
```

Expected: PASS.

**Step 2: Rebuild/recreate runtime if needed**

Run:

```bash
make restart
```

Expected: services recreate successfully.

**Step 3: Verify container mounts**

Run:

```bash
docker inspect team-nexus-atlas-gateway --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' | grep -E '/workspace|/workspaces|/opt/data'
```

Expected: repo mounted to `/workspace`, runtime workspaces mounted to `/workspaces`, runtime data mounted to `/opt/data`.

**Step 4: Verify Forge terminal cwd and GitHub env passthrough without printing secrets**

Run a short Forge profile command inside the container that uses the terminal tool or direct Hermes shell. The important assertion is:

```text
cwd=/workspaces/forge
GITHUB_TOKEN present len=40; CONTEXT7_API_KEY/STITCH_API_KEY present if set in `.env`
```

Do not print the token value.

**Step 5: Verify private repo access from terminal subprocess**

Inside a Forge terminal subprocess, run a redacted `git ls-remote` check against the private repo using `GITHUB_TOKEN`. Expected: return code 0. Redact token from any stderr/stdout.

---

## Rollback Plan

If the change breaks runtime startup:

1. Revert profile `terminal.cwd` values to `/workspace`.
2. Remove `/workspaces` mount from `docker-compose.profiles.yml`.
3. Leave `terminal.env_passthrough: [GITHUB_TOKEN]` in place if GitHub private repo access is still needed.
4. Run `make profile-render && make restart`.

## Decision Log

- 2026-05-12: Apply env passthrough to all active profiles, including Atlas. Approved passthrough vars: `GITHUB_TOKEN`, `CONTEXT7_API_KEY`, `STITCH_API_KEY`.

