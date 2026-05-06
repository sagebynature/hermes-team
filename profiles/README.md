# Team Nexus Profile Specs

This directory contains the repo-visible source of truth for the Hermes-native profile-driven Team Nexus architecture.

Current shape:

- `team-nexus.profiles.yaml` — lightweight roster and Team Nexus invariants: active/planned profiles, source dirs, gateway policy, checkpoint policy, role manifests, Kanban conventions, and safety policy.
- `profiles/<profile>/SOUL.md` — hand-maintained character, intent, persona, voice, and boundaries.
- `profiles/<profile>/AGENTS.md` — hand-maintained profile-specific operating instructions.
- `profiles/<profile>/config.yaml` — hand-maintained native Hermes config. Do not mirror the full Hermes config schema in `team-nexus.profiles.yaml`.
- `shared/profile/AGENTS.base.md` — shared Team Nexus guardrails composed into generated profile `AGENTS.md` during staging.

Related files:

- `shared/config/profile-spec-schema.md` — lightweight schema contract.
- `scripts/validate-profile-spec.py` — validates roster invariants and profile source files.
- `scripts/render-profile-spec.py` — dry-run/staging renderer that copies SOUL/config and composes AGENTS.
- `docker-compose.profiles.yml` — profile-driven Docker function-service skeleton: Atlas gateway, dashboard, admin shell, and one-shot dispatcher nudge.
- `shared/skills/manifests/` — shared base and role-specific skill manifests.

Ownership rules:

- Repo-owned: profile roster, `profiles/<profile>/` source files, shared AGENTS guardrails, shared skill manifests, Kanban/Discord workflow conventions.
- User/runtime-owned: `.env`, auth tokens, gateway tokens, live sessions, profile-local memory, logs, checkpoint data, live Kanban DB contents.

Bootstrap tooling stages profile homes from these sources with dry-run/diff behavior. It must not write directly into runtime-owned Hermes homes.
