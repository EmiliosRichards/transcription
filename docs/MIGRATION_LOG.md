# Migration Log

Timestamped record of deployments, migrations, and infrastructure changes for the transcription system.

---

## 2026-04-02 — Documentation overhaul

- **What:** Created ARCHITECTURE.md, DEPLOYMENT.md, SCHEMA.md, MIGRATION_LOG.md
- **Why:** Codebase split across two repos (standalone + monorepo) needed clear documentation before unification
- **Commit:** (this commit)

## 2026-03-24 — Server migration: 173.249.24.215 → 185.216.75.247

- **What:** Full migration of transcription API + worker to new production server
- **Why:** Server consolidation — new server already hosted the `dialfire` database with source tables
- **Changes:**
  - Database target changed from `manuav` to `dialfire` (media_pipeline schema restored into it)
  - DNS for `transcribe.vertikon.ltd` updated to 185.216.75.247
  - Added `metadata JSONB` column to `media_pipeline.audio_files` for per-job prompt support
  - Created `emilios` user on new server for service ownership
  - Installed Caddy for reverse proxy + auto SSL
  - Created systemd services for API and worker
  - Committed 7 previously untracked worker scripts to git
  - Discovered and documented dbsync2 lock contention issue on `contacts` table
- **Commit:** `e073341`, `ee5541a`
- **Deployed by:** Emilios

## 2025-09-07 through 2025-09-10 — Original API build

- **What:** Built and deployed the transcription gateway API + worker
- **Components:** media_router.py, gateway.py, transcribe_gpt4o.py, media_pipeline schema
- **Server:** 173.249.24.215
- **Database:** `manuav`
- **Commits:** `139dee2` → `1cdacba`
- **Deployed by:** Emilios

## 2026-03-10 — Monorepo import

- **What:** Transcription codebase imported into `manuav-platform` monorepo via `git subtree`
- **Changes:**
  - Directory restructured: `chatbot_app/backend/` → `api/`, `chatbot_app/frontend/` → `web/`
  - Backend refactored: new `transcription` schema, ORM models, dedicated worker.py, job queue with attempt tracking
  - Dual-database support added (platform + legacy Dialfire)
  - Alembic migrations added
- **Status:** Code exists in monorepo but has NOT been deployed to production. Production still runs the standalone repo version.
- **Note:** `prompt` parameter was removed in the refactor — needs to be ported back before deployment

---

## Pending

- [ ] Unify code: port `prompt` and `pitch_template` features into monorepo
- [ ] Deploy monorepo version to production
- [ ] Migrate data from `media_pipeline` → `transcription` schema
- [ ] Set up staging environment on 173.249.24.215
