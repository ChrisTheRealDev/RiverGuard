> Audit snapshot, 22 October 2026. Raw databases, personal transcripts, screenshots, logs and session material are excluded. Findings remain unfixed.

# RiverGuard security, lifecycle and distribution audit — 22 October 2026

Audit only. No application fixes were made. Production storage, credentials, model selection and the shipped ZIP were not changed. Reproductions used temporary directories/databases, synthetic markers, mocked generation, or an isolated ephemeral HTTP server. No model inference, cloud request, package download or broad dependency vulnerability scan was performed.

## Scope and result

Inspected `security.py`, `api.py`, `ui_api.py`, relevant `chat_service.py` startup/worker paths, `serve.py`, Windows setup/start/stop scripts, `package_app.py`, Python/npm/firmware dependency manifests, setup documentation, current ZIP members and historical release evidence. Read the access-control and supervisor tests. Root agent owns the broader browser/data/AI audit and full test run.

No authentication bypass was established in the inspected supported HTTP flows. The findings below concern confirmed packaging, availability and release-evidence gaps; they are not a claim that every attack or failure mode was tested.

| ID | Priority | Finding | Main source |
| --- | --- | --- | --- |
| SEC-01 | P2 | Recursive package inclusion can silently include private databases/configuration | `<workspace>/package_app.py:12` |
| OPS-01 | P2 | Dead inner background tasks leave the service reporting healthy/running | `<workspace>/ui_api.py:48` |
| OPS-02 | P2 | Second instance sharing a database classifies healthy replies as crashed | `<workspace>/chat_service.py:148` |
| OPS-03 | P2 | No finite graceful-shutdown deadline for open chat streams | `<workspace>/serve.py:58` |
| REL-01 | P3 | Manifest/smoke evidence describes a different ZIP | `<workspace>/output\redesign\RELEASE-CHECKLIST.md:67` |
| DOC-01 | P3 | Friend README points to deliberately omitted release evidence | `<workspace>/README.md:75` |

## SEC-01 — Packaging is not a strict file allowlist

**Confirmed in an isolated extracted copy.** Lines 12–14 recursively include almost every file under `assets`, `hardware`, `evaluation`, `tests` and `frontend`. The post-build assertion at line 29 rejects only `.db`, `.log` and exact `.env`/`secrets.toml` names. Thus `.sqlite3`, `.sqlite`, `.db-wal`, `.env.local` outside frontend, credential backups and other private files are not reliably excluded. The text scanner at lines 18–20 covers selected extensions and two API-key formats; it is not a general credential/privacy gate.

Reproduction: extract the current ZIP into a temporary directory; add synthetic `frontend/audit-export.sqlite3` and `hardware/.env.local`; run that copy's unchanged `package_app.py`. It exits 0 and the newly created temporary ZIP includes both files. Neither marker contained real credentials. The actual shipped ZIP currently contains neither of these files.

Impact: a future friend package can silently include private data placed in one of these source trees, contrary to the documented exclusion guarantee. This is a packaging guard failure, not evidence of an actual credential leak in the current archive.

Suggested repair, not implemented: restrict included trees to explicit source/asset types and reviewed files; reject private file patterns case-insensitively before writing the archive; validate every resolved source path remains inside the project; add synthetic private-file regression cases. Treat secret scanning as supplementary protection.

## OPS-01 — Background failure is invisible to health/supervision

**Confirmed with isolated fault injection.** `Simulation.start` creates an unobserved task at `<workspace>/ui_api.py:48`; `run` calls `core.save` without failure recovery at line 59. `GET /health` at line 188 always returns OK. `<workspace>/serve.py:60` and line 96 supervise the two Uvicorn serving tasks, not simulation or the chat worker created at `<workspace>/chat_service.py:152`.

A temporary-DB TestClient run injected `sqlite3.OperationalError('database or disk is full')` at simulation save. Observed: `simulation_task_done=true`, error type `OperationalError`, declared `state.running=true`, and `/health` status 200. The running production application was not faulted. A real disk/SQLite failure is a plausible trigger; it was not observed in production during this audit.

Impact: the launcher can appear healthy while simulation is permanently stopped; changing its running flag does not recreate the dead task. Equivalent unhandled chat-worker failures can leave accepted jobs unserviced, though that second failure path was source-reviewed rather than reproduced here.

Suggested repair: explicitly supervise required background tasks, distinguish degraded service health, surface actionable failures, and choose bounded recovery or fail-fast shutdown. Add disk/lock failure tests beyond checking Uvicorn task exits.

## OPS-02 — No database-level single-instance ownership

**Confirmed with two isolated service instances and mocked generation.** Startup at `<workspace>/chat_service.py:148` treats every queued/generating row as interrupted. The launcher checks ports at `<workspace>/serve.py:123`, but there is no database-owner lease/lock. Starting a second server on different valid ports while pointing it at the same database is therefore not excluded.

Observed in a temporary database: first service remained started with a healthy blocked mocked stream; its job was `generating`. Starting a second `ChatService` changed that same job to `failed` with “The app stopped before this reply finished.” No real model was contacted. In a two-server deployment both simulation lifespans would also start; duplicate simulation and independently owned workers are source-supported consequences, not separately measured here.

Impact: an accidental second instance can invalidate an active reply and violate the intended single-owner processing model. Distinct isolated databases, as recommended for review, avoid this; the executable does not enforce it.

Suggested repair: acquire exclusive process ownership or a robust lease per resolved database before recovery/worker startup; refuse a live owner. Distinguish recovery after a dead process from a healthy second process. Test contention between independent instances.

## OPS-03 — Graceful shutdown can wait indefinitely for SSE

**Confirmed server mechanism; application consequence supported by source.** Both configurations at `<workspace>/serve.py:58` omit `timeout_graceful_shutdown`; installed Uvicorn's effective value is `None`. The supervisor waits for a serving task at line 96 before setting the sibling's shutdown flag at line 100. Rill cancellation happens in the web lifespan after connection draining (`<workspace>/ui_api.py:159` onward).

An isolated ephemeral Uvicorn server with these defaults and a never-ending synthetic SSE response stayed alive after `should_exit=true`; it completed after the client closed the stream. This reproduction did not stop or alter RiverGuard. A normal Rill request may merely delay Ctrl+C until it finishes; a stuck/dead-worker job can keep its event observer open without a terminal event.

Impact: the documented Ctrl+C shutdown has no finite upper bound while chat streams remain open. `Stop RiverGuard.cmd` is an available forceful workaround, but does not provide a graceful drain guarantee.

Suggested repair: signal application jobs/observers before waiting for all connections, and use a finite graceful-shutdown deadline with documented recovery semantics. Add an integration test that stops the supervisor with an active blocked stream and proves bounded exit.

## REL-01 — Current artifact and historical evidence do not match

**Confirmed without rebuilding the production ZIP.** Actual `<workspace>/dist\RiverGuard-Windows.zip`: 102 members, 4,464,510 bytes, SHA256 `fc36d319595c95c93181698c59870918ce41950e37034b0a449ce9f1b4f7dd39`; CRC test passed. Every archived member byte-matched its current source file. The current artifact itself is therefore current with the working source inspected here.

However, `<workspace>/output\redesign\package-manifest.json:3`–5 and `<workspace>/output\redesign\RELEASE-CHECKLIST.md:67` describe 95 files, 4,444,565 bytes and SHA256 `ebbd0928d1ed0a04d9a8855a4983f6d07d263354941e9b9da2d4498445b55cb0`. The referenced extracted-package smoke result also states it reused the existing verified environment rather than testing a clean install.

Impact: those older smoke/manifest results cannot be attributed to the current ZIP by hash; a friend or reviewer cannot tell which exact artifact received the documented acceptance checks.

Suggested repair: generate artifact-specific manifest/evidence from the final archive and tie package smoke results to its checksum. Preserve older evidence as explicitly historical. This audit did not update either artifact or evidence.

## DOC-01 — Missing referenced acceptance evidence in friend package

**Confirmed by archive inventory.** The shipped README at `<workspace>/README.md:75` sends readers to the release checklist for measured speed/quality limits, and line 83 locates it under `output/redesign`. The packager intentionally omits that directory; the current ZIP has no `RiverGuard/output/redesign/RELEASE-CHECKLIST.md` or release-evidence files.

Suggested repair: ship a sanitized release/limitations summary at a documented included path, or make these links clearly development-workspace-only. Retain the exclusion of private review databases, owner links and logs.

## Checks that held / limitations

- Session tokens and device credentials are hashed in SQLite; browser cookies are HttpOnly/SameSite Strict. Mutations require a matching Origin and per-session CSRF value. Bootstrap is short-lived, one-use and loopback-only. Pair codes are expiring/one-use and invalid attempts commit their rate counters. No bypass was established in source review or the existing isolated regressions.
- Device bearer credentials are scoped to their own station's ingest/configuration reads; they do not satisfy browser-session authorization. Credential rotation invalidates the old token. SQL parameters are bound in the inspected access paths.
- The web service rejects foreign Host values, redacts configured endpoint userinfo from session metadata, bounds JSON request bodies, and rechecks session validity before forwarding each SSE event. These are positive findings, not a penetration-test guarantee.
- Public health, static interface, mascot and reviewed setup-guide assets are expected unauthenticated resources. This audit did not identify private readings/chats in those resources.
- HTTP transport and private-network trust are explicitly documented. Pairing does not encrypt traffic; physical access, trusted paired-device privileges and OS-level access remain outside application authorization.
- `pip check` in the existing environment reported no broken requirements. Versions are pinned in `requirements-lock.txt`; npm and PlatformIO manifests/locks were inspected. No clean-machine installation or new vulnerability/advisory network scan was performed. Existing environment success does not establish clean-install success on every Windows/Python architecture.
- Current ZIP CRC, source byte comparison and private-name inventory passed. That is a bounded inspection of today's archive, separate from SEC-01's confirmed future packaging guard gap.
- Security tests cover basic auth/CSRF/origin, expiry/revocation, station mismatch/rotation, host rejection and body bounds. Missing coverage includes private-file injection in packaging, live second-owner recovery, internal task failure reporting, and bounded shutdown with an active SSE stream.
- Existing README benchmark instructions target the fixed local `llama3.2:3b` script (`<workspace>/benchmark_rill_quality.py:171`); that script deliberately does not read the persisted selector. It should not be treated as acceptance evidence for a newly selected model. No benchmark was run in this audit.
