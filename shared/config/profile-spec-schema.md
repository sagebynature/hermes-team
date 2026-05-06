# Team Nexus profile spec schema

Status: Draft
Source spec: `profiles/team-nexus.profiles.yaml`

This document describes the initial schema that profile bootstrap/validation tooling should enforce. It is intentionally lightweight until the renderer is implemented.

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
| `gateway.enabled` | Whether this profile runs a gateway in v1. |
| `checkpoints.enabled` | Whether filesystem checkpoints are enabled by default. |

Active v1 profiles should also define:

- `summary`
- `skills.base`
- `skills.role_manifest`
- `owns`

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

Preview generated host profile files without writing profile homes:

```bash
make profile-render-dry-run
```

Preview Docker-mode path substitutions:

```bash
make profile-render-docker-dry-run
```

Materializing files requires an explicit staging directory:

```bash
python3 scripts/render-profile-spec.py --mode host --write --output-dir /tmp/team-nexus-profile-render
```

The renderer intentionally refuses to write directly into runtime-owned Hermes homes.
