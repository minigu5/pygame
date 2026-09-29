# Player Poses and Sizes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give each player three size choices and three poses, with identical appearance and collision dimensions on server and client.

**Architecture:** Store pose and size in each authoritative server body. Define dimensions in shared tuning data. Validate shape changes against map collision, include shape state in snapshots, and use same dimensions in client prediction, rendering, room focus, and accusation checks.

**Tech Stack:** Python 3.13+, pygame-ce, TypeScript, shared JSON tuning data.

**Spec:** `docs/superpowers/specs/2026-09-29-lobby-shapes-cleanup-design.md` section 2.

## Global Constraints

- Keep standing normal body at 24×32px.
- Pose bases: stand 24×32px, crouch 24×20px, lie 36×16px.
- Size factors: small 0.5, normal 1, large 1.5; round dimensions to positive integer pixels.
- Store one shared preset table in `shared/tuning.json`.
- Server validates every shape request and remains authoritative.
- Reset all players to normal standing pose at round start.

## Review Focus

- Requested dimensions collide with wall; reject without changing position or pose.
- Grounded resize; preserve feet and horizontal center.
- Airborne resize; preserve body center and velocity.
- Shape changes near ladders or room boundaries; use new dimensions consistently.
- Invalid enums, spectator, and caught-player requests; ignore without mutating state.

---

### Task 1: Define shared presets and dimension helpers

**Files:**
- Modify: `shared/tuning.json`
- Modify: `server/src/physics.ts`
- Modify: `client/physics.py`

**Interfaces:**
- Shared `shape_sizes` maps each pose to base width/height; `shape_scales` maps size names to numeric factors.
- Server and client expose equivalent dimension helpers that return integer `{width, height}` from pose and size.
- `Body` gains `pose` and `size`, defaulting to `stand` and `normal`.

- [ ] Add exact pose bases and size factors to `shared/tuning.json`.
- [ ] Add server dimension helper and use body-specific dimensions in overlap, ladder detection, and movement collision.
- [ ] Add equivalent Python helper and replace fixed tuning width/height use in physics.
- [ ] Preserve current server/client step parity for default normal standing body.

### Task 2: Validate server shape changes and publish state

**Files:**
- Modify: `server/src/protocol.ts`
- Modify: `server/src/room.ts`
- Modify: `server/src/physics.ts`

**Interfaces:**
- Client message: `{t: "shape", pose: "stand" | "crouch" | "lie", size: "small" | "normal" | "large"}`.
- Snapshot `me` and each `PlayerView` include `pose` and `size`.
- Server helper attempts transition; returns false if target dimensions overlap solid tiles.

- [ ] Add shape message and snapshot fields to protocol types.
- [ ] Validate pose and size against explicit allowed values before transition.
- [ ] Reject spectators and caught players.
- [ ] Preserve feet while grounded and center while airborne; preserve velocity and other movement state.
- [ ] Reject target size if collision map overlaps at adjusted position.
- [ ] Apply player-specific dimensions to room-center calculation and hunter accusation rectangle.
- [ ] Reset pose and size in `startRound()`.

### Task 3: Apply shape changes to prediction and input

**Files:**
- Modify: `client/main.py`
- Modify: `client/predict.py`
- Modify: `client/physics.py`

**Interfaces:**
- Pose is chosen with `Down`/`Up` and the pose bar (client side done 2026-09-29, freeze mode only); `1`-`4` belong to the brushes, so size keys are still to be picked.
- Predictor reconciliation reads `pose` and `size` from authoritative snapshot before replaying unacknowledged movement.

- [ ] Map numeric key events to requested size and pose.
- [ ] Send `shape` message and apply same request to local predicted body immediately.
- [ ] Update body pose and size from each authoritative snapshot before replaying input history.
- [ ] Stop local shape input after caught state or spectator role.
- [ ] Keep paint panel controls and movement bindings unchanged.

### Task 4: Render shapes and communicate controls

**Files:**
- Modify: `client/render.py`
- Modify: `client/main.py`
- Modify: `client/hud.py`
- Modify: `client/predict.py`

**Interfaces:**
- Render player uses snapshot `pose` and `size` to calculate rectangle dimensions.
- HUD shows current pose/size and six numeric key bindings.

- [ ] Draw each player with its own snapshot dimensions, including interpolated remote players.
- [ ] Use local predicted dimensions for local player, camera focus, and minimap position.
- [ ] Show current selected shape and control legend in HUD.
- [ ] Preserve current player color and outline rendering.

### Task 5: Update documentation and review feature

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-21-chameleon-design.md`
- Modify: `docs/superpowers/specs/2026-09-21-meccha-chameleon-2d-game-spec.md`

- [ ] Document size/pose controls, collision behavior, and round reset.
- [ ] Record shared preset source and snapshot state in technical design.
- [ ] Review all fixed-dimension call sites across client, server, spawn spacing, camera, minimap, and accusation logic.
- [ ] Stage only files for issue #12.
- [ ] Commit on feature branch with message `feat: add player poses and sizes`.

