# Branch Naming — for work against this fork's modularity issues

Adopted from the shared-services governance standard
(`shared-services/docs/standards/BRANCH-NAMING-GUIDE.md`) for consistency
across repos this maintainer works in. Not part of upstream `aayushch/laya`.

Format: `{prefix}/{description}`, lowercase, hyphen-separated, issue number optional.

| Prefix | Use for |
|---|---|
| `fix/` | Bug fixes |
| `refactor/` | Boundary/seam fixes, god-file splits (most of M2/M3 here) |
| `ci/` | CI/CD workflow changes (M1, M4) |
| `infra/` | Build/packaging/release script changes (M4) |
| `chore/` | Hygiene, dead-file removal (M5) |
| `epic/` | Branches spanning a whole epic |

Example: `refactor/eventbus-websocket-decoupling` for issue #6 (M2).

Not allowed: `feature/`, `wip/`, `tmp/`, `draft-`, uppercase, underscores.
