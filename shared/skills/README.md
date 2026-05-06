# Shared skills

Team-wide skills live here as canonical repo-visible source material. Profile skill manifests in `shared/skills/manifests/` declare which skills each Team Nexus profile should receive or reference.

Rendered Docker profile homes live under:

```text
runtime/hermes/profiles/<profile>/
```

Do not commit rendered runtime skill state, auth files, sessions, memory, logs, or checkpoints. Durable skill source belongs in this directory tree or in upstream Hermes skill packages.
