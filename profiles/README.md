# Team Nexus Profile Specs

This directory contains the repo-visible source of truth for the planned Hermes-native profile-driven Team Nexus architecture.

Current skeleton:

- `team-nexus.profiles.yaml` — v1 profile roster, runtime modes, gateway policy, Kanban conventions, workspace policy, safety policy, and knowledge policy.

Ownership rules:

- Repo-owned: profile roster, role definitions, SOUL/AGENTS templates, shared skill manifests, default config fragments, Kanban/Discord workflow conventions.
- User/runtime-owned: `.env`, auth tokens, gateway tokens, live sessions, profile-local memory, logs, checkpoint data, live Kanban DB contents.

Bootstrap tooling should render host and Docker profile homes from these specs with dry-run/diff/backup behavior before overwriting managed files.
