# Protocol and Map Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove unused door metadata, remove misleading role from `hello`, and show readable connection failures.

**Architecture:** Delete `doors` at map generation and in generated JSON/docs. Make first snapshot sole role authority. Convert known WebSocket handshake and network failures into Korean user messages before they reach the game HUD.

**Tech Stack:** Python 3.13+, pygame-ce, TypeScript, JSON.

**Spec:** `docs/superpowers/specs/2026-09-29-lobby-shapes-cleanup-design.md` section 3.

## Global Constraints

- Preserve actual role in snapshots and join notifications.
- Keep `hello` ID, tick, and map fields.
- Room doorways remain collision-map gaps.
- Never show raw Python exception text in game UI.
- No new runtime dependencies.

## Review Focus

- Old generated map contains `doors`; remove field without changing tiles, rooms, or spawn values.
- Existing clients read `hello.role`; remove all runtime dependencies on that field.
- HTTP 409 and 400 handshake responses map to correct Korean messages.
- DNS, TLS, refused connection, and timeout errors map to useful generic network guidance.
- Unexpected WebSocket rejection still produces a short safe message.

---

### Task 1: Remove unused door metadata

**Files:**
- Modify: `tools/make_building_map.py`
- Modify: `shared/map_01.json`
- Modify: `docs/superpowers/specs/2026-09-21-chameleon-design.md`

- [ ] Remove `doors` list construction and output from map generator.
- [ ] Remove only `doors` property from generated map JSON; preserve all other map values.
- [ ] Remove `doors` format example and dead-data claims from technical design.
- [ ] Keep movement through door openings determined by existing solid-tile layout.

### Task 2: Remove role claim from connection greeting

**Files:**
- Modify: `server/src/protocol.ts`
- Modify: `server/src/room.ts`
- Modify: `client/main.py`
- Review: `tools/check_physics_parity.py`, `tools/smoke_ws.py`

- [ ] Remove `role` from `hello` server message type and payload.
- [ ] Keep client ID handling; set role only from `snapshot.me.rl`.
- [ ] Check scripts for `hello.role` access and remove any such dependency.
- [ ] Keep real roles in `j` notifications and snapshots.

### Task 3: Map connection failures to user messages

**Files:**
- Modify: `client/net.py`
- Modify: `client/main.py`

**Interfaces:**
- `Connection.error` contains user-facing Korean text or `None`; never raw exception class or traceback.
- HTTP 409 maps to full-room text, HTTP 400 maps to invalid-room-code text, and transport failures map to server/network guidance.

- [ ] Inspect WebSocket handshake exception status through its response object.
- [ ] Map 409, 400, transport failure, and unknown handshake failure to stable Korean sentences.
- [ ] Keep game loop alive long enough to render connection failure and allow exit.
- [ ] Remove any raw exception display path from status rendering.

### Task 4: Review and commit cleanup

**Files:**
- Review files from Tasks 1–3.

- [ ] Search source, generated map, and docs for remaining `doors` protocol metadata and `hello.role` assumptions.
- [ ] Stage only files for issue #15.
- [ ] Commit on feature branch with message `fix: clarify connection errors and remove stale fields`.

