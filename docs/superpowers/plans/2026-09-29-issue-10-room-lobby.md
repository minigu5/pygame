# Room Lobby Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let players browse active rooms, join listed rooms, and create rooms with custom phase lengths while keeping direct room-code connection.

**Architecture:** Add one SQLite-backed `RegistryDO` for room metadata. `RoomDO` publishes occupancy and phase changes, then sends a 30-second heartbeat. Worker exposes `GET /rooms`; pygame client shows a lobby and uses existing WebSocket room connection to create or join rooms.

**Tech Stack:** Python 3.13+, pygame-ce, Python standard library HTTP/threading, TypeScript, Cloudflare Workers and Durable Objects.

**Spec:** `docs/superpowers/specs/2026-09-29-lobby-shapes-cleanup-design.md` section 1.

## Global Constraints

- Keep `--room CODE` and current `hide`, `seek`, `result` URL options working.
- Room capacity remains `tuning.max_players`.
- Registry stores room code, player count, capacity, phase, and last update only.
- Never store or return player IDs, positions, or colors in room listings.
- Registry errors must not block WebSocket gameplay.
- Add no runtime dependencies.

## Review Focus

- Last player disconnects while a registry update is in flight; remove room idempotently.
- Active room heartbeat races with last-player removal; stale heartbeat must not recreate an empty room.
- Registry timeout or malformed response; lobby remains responsive and supports retry.
- Generated code matches `/^[a-z0-9-]{1,32}$/` and room options remain within existing bounds.
- Room phase changes while lobby is open; refresh returns current phase and occupancy.

---

### Task 1: Add room registry and Worker route

**Files:**
- Create: `server/src/registry.ts`
- Modify: `server/src/worker.ts`
- Modify: `server/src/room.ts`
- Modify: `server/wrangler.jsonc`

**Interfaces:**
- `RegistryDO.fetch`: `GET /rooms` returns JSON list; internal `PUT /room` upserts `{code, players, capacity, phase, updatedAt}`; internal `DELETE /room?code=CODE` removes entry.
- `RoomDO` calls `REGISTRY.get(REGISTRY.idFromName("rooms"))` using its environment binding.
- Worker public API exposes only `GET /rooms`; `/ws` remains unchanged.

- [ ] Add typed Worker environment with `ROOM` and `REGISTRY` Durable Object namespaces.
- [ ] Implement `RegistryDO` using Durable Object storage; validate internal payloads and room code before writes.
- [ ] Add `GET /rooms` routing and return `405` for unsupported methods.
- [ ] Add `REGISTRY` binding and SQLite class migration in `server/wrangler.jsonc`.
- [ ] Keep registry list response free of internal timestamps and player identifiers.

### Task 2: Publish live room metadata

**Files:**
- Modify: `server/src/room.ts`
- Modify: `server/src/registry.ts`

**Interfaces:**
- `RoomDO.publishRoomState()` builds registry metadata from room code, `players.size`, `tuning.max_players`, and `clock.phase`.
- `RoomDO` calls publish after join, disconnect, round start, phase advance, and round finish.

- [ ] Save room code from first WebSocket URL for registry updates.
- [ ] Publish after each occupancy or phase transition.
- [ ] Publish heartbeat at 30-second intervals while room has players.
- [ ] Swallow and record no user-visible failure when registry request fails; continue room ticks and socket handling.
- [ ] Delete registry entry after last player leaves; make deletion safe to repeat.
- [ ] Prune entries older than 90 seconds during `GET /rooms` and before returning list.
- [ ] Prevent stale heartbeat from restoring room entry after `players.size` becomes zero.

### Task 3: Build lobby screen and room-list fetch

**Files:**
- Create: `client/lobby.py`
- Modify: `client/net.py` or add a focused standard-library HTTP worker module under `client/`

**Interfaces:**
- `Lobby.run(screen, server_url)` returns selected `{room, hide, seek, result}` or `None` on quit.
- Room list fetch runs off pygame main thread and reports either validated room rows or a displayable error.

- [ ] Convert `ws://` to `http://` and `wss://` to `https://` for `/rooms` requests.
- [ ] Fetch room list in a background thread with a finite timeout and a queue back to pygame.
- [ ] Draw room code, player count/capacity, phase, selection, refresh action, and empty/error states.
- [ ] Add join action for selected room.
- [ ] Add create action with bounded integer controls for hide, seek, and result lengths.
- [ ] Generate a lowercase alphanumeric/hyphen room code within 32 characters for new rooms.
- [ ] Keep all UI text Korean and use project font fallback pattern.

### Task 4: Route startup through lobby and document use

**Files:**
- Modify: `client/main.py`
- Modify: `README.md`

**Interfaces:**
- `--room CODE` selects direct-connect mode.
- Missing `--room` opens lobby; chosen options become existing WebSocket query parameters.

- [ ] Change `--room` default to `None` and start pygame before choosing lobby or direct-connect mode.
- [ ] Connect with selected code and phase options after lobby returns.
- [ ] Preserve direct room mode for scripts and command-line links.
- [ ] Document lobby launch, direct room launch, listed room fields, and room settings.

### Task 5: Review and commit feature

**Files:**
- Review files from Tasks 1–4.

- [ ] Review registry privacy, update ordering, failure isolation, and stale-entry rules.
- [ ] Review lobby loading, retry, creation, and direct-connect paths.
- [ ] Stage only files for issue #10.
- [ ] Commit on feature branch with message `feat: add room lobby`.

