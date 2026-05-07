# Team Nexus profile spec schema

Status: Draft
Source spec: `profiles/team-nexus.profiles.yaml`

This schema is intentionally lightweight. Team Nexus owns roster/runtime invariants here, while native Hermes config remains hand-maintained in each `profiles/<profile>/config.yaml`.

## Top-level required keys

| Key | Purpose |
|---|---|
| `version` | Spec version for future migrations. |
| `status` | Draft/proposed/active marker. |
| `runtime` | Host/Docker runtime policy. |
| `interfaces` | Discord/dashboard/admin surfaces. |
| `kanban` | Board, tenant, metadata, and comment conventions. |
| `workspace` | Worktree/scratch workspace defaults. |
| `knowledge` | Learning and skill hierarchy. |
| `profiles` | Profile roster and role definitions. |
| `secrets` | Secret handling policy. |
| `verification_required_before_done` | Done-check checklist. |

## Profile entry required keys

Each `profiles.<name>` entry should define:

| Key | Purpose |
|---|---|
| `status` | `active_v1`, `planned_inactive`, or future lifecycle value. |
| `display_name` | Human-facing name. |
| `one_job` | Compact role charter. |
| `source_dir` | Canonical source directory, usually `profiles/<profile>`. |
| `gateway.enabled` | Whether this profile runs a gateway in v1. |
| `checkpoints.enabled` | Whether filesystem checkpoints are enabled by default. |
| `skills.base_manifest` | Shared skill manifest path. |
| `skills.role_manifest` | Role skill manifest path for active profiles. |

Active v1 profiles should also define:

- `summary`
- `owns`

## Canonical profile source directory

Each `source_dir` must contain:

- `SOUL.md` — hand-maintained character, intent, persona, voice, and boundaries.
- `AGENTS.md` — hand-maintained profile-specific operating instructions.
- `config.yaml` — hand-maintained native Hermes config.

The renderer stages these files as follows:

- `SOUL.md` is copied unchanged.
- `config.yaml` is copied unchanged.
- `AGENTS.md` is composed from `shared/profile/AGENTS.base.md` plus `profiles/<profile>/AGENTS.md`.

## Native Hermes config policy

Do not mirror Hermes' full `config.yaml` schema in `team-nexus.profiles.yaml`. The validator only checks lightweight invariants needed by Team Nexus, such as:

- profile source files exist and are non-empty;
- `config.yaml` parses as YAML;
- `config.yaml.model.provider` and `config.yaml.model.default` exist for each profile;
- active role manifests exist;
- Atlas is the only v1 gateway profile;
- worker gateways are disabled in the roster.

## Non-overwrite boundary

Generated/bootstrap-managed files must be clearly separated from runtime-owned files. Tooling must not overwrite:

- `.env`
- auth/token files
- sessions
- memory
- logs
- gateway state
- checkpoint data
- live Kanban DBs

## Validation command

Run:

```bash
make profile-validate
```

or directly:

```bash
python3 scripts/validate-profile-spec.py profiles/team-nexus.profiles.yaml
```

## Render dry-run command

Preview generated profile files without writing profile homes:

```bash
make profile-render-dry-run
```

Preview Docker-mode staging label; config is still copied unchanged:

```bash
make profile-render-docker-dry-run
```

Materializing files requires an explicit staging directory:

```bash
python3 scripts/render-profile-spec.py --mode host --write --output-dir /tmp/team-nexus-profile-render
```

The renderer intentionally refuses to write directly into runtime-owned Hermes homes.
