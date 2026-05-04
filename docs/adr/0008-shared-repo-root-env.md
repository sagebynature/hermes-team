# ADR-0008: Load shared secrets from the repo-root .env

Status: Accepted

Date: 2026-05-04

## Context

All agents need common provider keys and gateway settings. Duplicating `.env` files across each agent home would increase setup friction and drift. Baking secrets into the image is unacceptable.

## Decision

Use one repo-root `.env` loaded by every Compose service via:

```yaml
env_file:
  - ./.env
```

Keep `.env.example` committed with placeholders only.

## Consequences

Positive:

- Simple bootstrap.
- One place to rotate shared provider keys.
- Secrets stay out of the image.
- Compose behavior is easy to inspect.

Tradeoffs:

- All agents receive the same shared environment variables.
- Per-agent credential separation requires agent-local auth state or future per-agent env files.

## Implementation notes

Start from:

```bash
cp .env.example .env
```

Do not commit `.env`.

Use agent mounted homes for distinct OAuth state, credential pools, sessions, and auth files.

