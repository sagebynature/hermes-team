# ADR-0014: Big-bang refactor to Hermes-native profile-driven Team Nexus

Status: Accepted
Date: 2026-05-06
Supersedes: ADR-0011, ADR-0012, and per-agent-runtime portions of ADR-0001/0006 where they conflict with this decision.

## Context

Team Nexus has been moving as a Docker-per-agent, registry-generated, Compose-dispatched multi-agent system. That architecture provided visible agent identity and operational separation, but it also created pain:

- custom router/dispatcher complexity,
- agents could feel performative unless backed by durable evidence,
- inspection/debugging required too much bespoke state,
- Docker and config management overhead slowed iteration,
- profile/skill/memory state could drift across agent homes.

Hermes now has native profile, Kanban, dashboard, gateway, and checkpoint primitives that map better to the desired Team Nexus direction.

The new north star is a Hermes-native, profile-driven multi-agent setup: software-delivery-first, expandable into a personal AI company, and modeled after Hermes reference architecture as much as possible.

## Decision

Refactor Team Nexus around native Hermes profiles and native Hermes Kanban.

Adopt a dual-mode runtime:

1. Host profile mode for fast local/operator iteration.
2. Docker profile mode using one Team Nexus image and function-level Compose services.

Docker remains first-class, but Docker containers are no longer the default unit of agent identity. Hermes profiles are.

V1 active profiles:

- Atlas: Mission Orchestrator and only Discord-facing bot.
- Forge: Implementation Engineer.
- Sentinel: Quality Gate Reviewer.
- Scribe: Documentation Specialist.
- Curator: Learning and Profile Steward.

Planned inactive profiles:

- Scout.
- Ops.
- Relay/Echo.

## Runtime model

Replace the old one-service-per-agent model with one image and function services:

- Atlas gateway / Discord bot.
- Dashboard.
- Gateway-embedded native Kanban dispatcher by default.
- Optional one-shot dispatcher nudge service.
- Optional admin/shell.

All function services share the generated Hermes profile set and workspace mounts. Workers are spawned as Hermes profiles by the dispatcher, not as separate Compose services.

A future sandbox path may use Docker for tasks marked `sandbox_required`, but per-agent containers are not the default identity or dispatch mechanism.

## Discord and gateway policy

Discord is the primary user surface: Discord is the CLI.

V1 uses only Atlas as a Discord gateway/bot. Worker profiles do not run Discord gateways by default.

Profile specs may contain optional worker gateway settings, disabled by default, to support future notification-only worker identities. If enabled later, worker bots must be evidence reporters only and may not become a worker-to-worker bus.

## Kanban policy

Kanban is the durable source of truth for multi-agent work.

- Coding work uses a board per project/repo.
- General work uses a default/general board.
- Coding-board tenant = mission/conversation identifier.
- General-board tenant = domain or mission.
- Native Kanban statuses remain authoritative.
- Metadata and structured comments carry mission/evidence details.

Atlas must cite Kanban evidence before claiming worker progress or completion.

## Coding and review policy

- Coding tasks use git worktrees by default.
- Forge implements, verifies, commits, and reports evidence.
- Sentinel reviews all source code changes, PR-bound work, and risk-sensitive dependency/security/runtime/config changes.
- PR-bound missions use draft PRs opened by Forge after implementation and reviewed by Sentinel.
- Atlas final responses include task IDs, branch/commit/PR/test/verdict evidence.

## Learning policy

Repo-visible learning is high importance.

Durable Team Nexus conventions, workflows, profile behavior, and reusable procedures should live in repo-visible docs/specs/skills unless clearly private/local.

Curator owns canonical skill/doc/profile learning updates. Other profiles emit `learning_candidate` comments rather than directly editing canonical skills during normal work.

## Checkpoint policy

Enable Hermes checkpoints for profiles that can edit files:

- Forge.
- Sentinel.
- Scribe.
- Curator.
- Ops later.
- Atlas if it edits files directly.

Checkpoints are a safety net, not a replacement for git worktrees/commits.

## Consequences

Positive:

- Stronger alignment with Hermes native profile/Kanban architecture.
- Less custom dispatcher/router glue.
- Better evidence model for real multi-agent delegation.
- Faster host iteration while preserving Docker runnability.
- Clearer distinction between user surface, worker bus, and inspection surface.
- Better repo-visible governance for learning and profile specs.

Tradeoffs:

- Less default OS/process isolation between agents.
- Requires new bootstrap/spec renderer discipline.
- Requires decisive cleanup of old per-agent services and generated artifacts.
- Atlas becomes the v1 gateway bottleneck.
- Board-per-project and Discord mission threads add workflow policy complexity.

Mitigations:

- Use Docker as sandbox escape hatch for risky tasks.
- Use checkpoints for editing profiles.
- Use git worktrees for coding tasks.
- Keep worker gateway tokens disabled by default.
- Require evidence-backed Discord finals and status.
- Require full verification before done.

## Migration approach

Use a big-bang replacement direction, staged internally:

1. Add profile-driven docs/spec skeleton.
2. Implement profile bootstrap/runtime path.
3. Switch defaults to profile-driven Docker/host mode.
4. Remove obsolete per-agent services/glue.
5. Verify host, Docker, dashboard, Discord, Kanban, and first vertical slice.
6. Leave no dead code behind.

## Acceptance criteria

The refactor is accepted when:

- Profile specs validate.
- Skills/manifests validate.
- Generated config dry-run/diff works.
- Docker image builds.
- Docker gateway/dashboard/dispatcher services start.
- Host bootstrap works or dry-run is validated.
- Kanban board/routing smoke test passes.
- First vertical slice works: Discord -> Atlas -> Forge -> Sentinel -> Scribe/Curator as needed -> Atlas final.
- Old per-agent-runtime dead code is removed.
- No secrets are committed or overwritten.
