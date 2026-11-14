---
name: skyfleet-start
description: Start the whole local SkyFleet dev environment after a reboot (Docker Desktop, PostgreSQL, FastAPI on 8000, Simulation Worker, Vite on 5173). Idempotent; reuses healthy services; never applies migrations or kills processes. Use `/skyfleet-start status` to only report.
argument-hint: "[status]"
disable-model-invocation: true
---

# SkyFleet Start

## Purpose
One command to bring the local environment up. All logic is in `start-skyfleet.ps1` (same folder); this skill runs it and reports honestly.

## Workflow
1. Run the helper with the PowerShell tool (timeout 600000 ms; startup can take minutes while Docker boots):
   - `/skyfleet-start` → `powershell -NoProfile -ExecutionPolicy Bypass -File .claude/skills/skyfleet-start/start-skyfleet.ps1`
   - `/skyfleet-start status` → the same command with `-StatusOnly` (starts nothing).
2. Relay the final status table: URLs, per-service state, log directory, and every failure with its reason.
3. If a step reports `OUTDATED`, `CONFLICT`, `STALE` or `FAILED`, explain the stated cause and the suggested manual action. Do not work around it.

## States
`OK` already healthy, reused · `STARTED` launched now and verified · `DOWN` (status mode) · `SKIPPED` a prerequisite failed · `OUTDATED` schema behind head · `CONFLICT` port used by something that is not SkyFleet · `STALE` worker process without a fresh heartbeat · `FAILED`.

## Hard rules
- NEVER run `alembic upgrade`/`downgrade`, or any migration. On `OUTDATED` show the command and stop.
- NEVER kill, restart or replace an existing process or container; never use `docker compose down`, `rm`, `prune`, `-v`, or touch the `skyfleet-db` volume.
- NEVER change a port; the helper uses `--strictPort` and reports conflicts.
- Do not read or print `.env*` files. Do not commit.
- Do not start a second worker: the helper checks both processes (`app.worker`) and the API's `worker_stale` flag (`GET /api/flights`, plus `simulation.worker_running` when present).
- With Feature 020 code, a started worker resets the simulation speed to 1x. Mention it if the worker was started.

## Logs and stopping
Each started service runs in its own minimized `cmd` window titled `SkyFleet API|Worker|Frontend` (close the window to stop it). Output is appended to `%LOCALAPPDATA%\SkyFleet\logs\{api,worker,frontend}.log`; inspect with `Get-Content <file> -Wait -Tail 50`.

## Prerequisites (manual)
Docker Desktop installed; `uv` on PATH with `backend\.venv` created (`uv sync`); `frontend\node_modules` installed (`npm install`). The helper never installs anything.
