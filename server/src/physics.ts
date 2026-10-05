import { isLadderAt, isSolidTile, map, tuning } from "./map";

export const LEFT = 1;
export const RIGHT = 2;
export const JUMP = 4;
export const UP = 8;
export const DOWN = 16;

export type Body = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  onGround: boolean;
  onLadder: boolean;
  frozen: boolean;
  coyoteMs: number;
  jumpBufferMs: number;
  jumpHeld: boolean;
};

export function spawnBody(at: [number, number]): Body {
  return {
    x: at[0],
    y: at[1],
    vx: 0,
    vy: 0,
    onGround: false,
    onLadder: false,
    frozen: false,
    coyoteMs: 0,
    jumpBufferMs: 0,
    jumpHeld: false,
  };
}

/** Advance one body by a single tick. `mask` is this frame's key bitmask. */
export function step(body: Body, mask: number, dtMs: number): void {
  const dt = dtMs / 1000;

  if (body.frozen) {
    // Pinned, not stuck: the keys slide the body slowly in any direction,
    // free of gravity, so it can be set exactly where it should hide.
    const slideX = ((mask & RIGHT) !== 0 ? 1 : 0) - ((mask & LEFT) !== 0 ? 1 : 0);
    const slideY = ((mask & DOWN) !== 0 ? 1 : 0) - ((mask & UP) !== 0 ? 1 : 0);
    if (slideX !== 0 || slideY !== 0) {
      // It may be left hanging in the air, so it is no longer standing on
      // anything: no stair step while sliding and no jump out of nowhere after.
      body.onGround = false;
      body.coyoteMs = 0;
      moveX(body, slideX * tuning.frozen_move_speed * dt);
      moveY(body, slideY * tuning.frozen_move_speed * dt);
    }
    body.vx = 0;
    body.vy = 0;
    return;
  }

  const wantsJump = (mask & JUMP) !== 0;

  // A ladder suspends gravity while the body is on it; jumping lets go.
  body.onLadder =
    isLadderAt(body.x + tuning.player_width / 2, body.y + tuning.player_height / 2) &&
    !wantsJump;
  if (body.onLadder) {
    body.jumpHeld = wantsJump;
    const climb = ((mask & DOWN) !== 0 ? 1 : 0) - ((mask & UP) !== 0 ? 1 : 0);
    body.vy = climb * tuning.climb_speed;
    body.vx =
      (((mask & RIGHT) !== 0 ? 1 : 0) - ((mask & LEFT) !== 0 ? 1 : 0)) * tuning.move_speed;
    moveX(body, body.vx * dt);
    body.onGround = moveY(body, body.vy * dt);
    body.coyoteMs = tuning.coyote_ms;
    return;
  }

  body.jumpBufferMs = wantsJump && !body.jumpHeld ? tuning.jump_buffer_ms : Math.max(0, body.jumpBufferMs - dtMs);

  // Releasing jump early cuts the rise short (short hop)
  if (!wantsJump && body.jumpHeld && body.vy < 0) {
    body.vy *= tuning.short_hop_factor;
  }
  body.jumpHeld = wantsJump;

  // Horizontal movement with acceleration/deceleration
  const direction = ((mask & RIGHT) !== 0 ? 1 : 0) - ((mask & LEFT) !== 0 ? 1 : 0);
  const targetVx = direction * tuning.move_speed;
  
  // Choose acceleration/deceleration based on whether we're on ground or in air
  let accel: number, decel: number;
  if (body.onGround) {
    accel = tuning.ground_accel;
    decel = tuning.ground_decel;
  } else {
    accel = tuning.air_accel;
    decel = tuning.air_decel;
  }
  
  // Apply acceleration/deceleration
  if (direction !== 0) {  // Trying to move
    if (body.vx * targetVx < 0) {  // Trying to reverse direction
      // Apply deceleration to stop, then acceleration in new direction
      if (body.vx > 0) {  // Currently moving right
        body.vx = Math.max(body.vx - decel * dt, targetVx);
      } else {  // Currently moving left
        body.vx = Math.min(body.vx + decel * dt, targetVx);
      }
    } else {  // Trying to continue in same direction
      if (body.vx < targetVx) {  // Need to speed up
        body.vx = Math.min(body.vx + accel * dt, targetVx);
      } else {  // Need to slow down (overshooting)
        body.vx = Math.max(body.vx - accel * dt, targetVx);
      }
    }
  } else {  // Not trying to move - apply deceleration to stop
    if (body.vx > 0) {
      body.vx = Math.max(body.vx - decel * dt, 0);
    } else if (body.vx < 0) {
      body.vx = Math.min(body.vx + decel * dt, 0);
    }
  }

  // Asymmetric gravity
  let gravityMult: number;
  if (body.vy < -80) {  // Moving upward fast
    gravityMult = 1.0;
  } else if (Math.abs(body.vy) < 80) {  // Near peak of jump
    gravityMult = 0.55;
  } else {  // Moving downward
    gravityMult = 1.5;
  }
  
  body.vy = Math.min(body.vy + tuning.gravity * gravityMult * dt, tuning.max_fall_speed);

  // Handle jump initiation
  if (body.jumpBufferMs > 0 && body.coyoteMs > 0) {
    body.vy = tuning.jump_speed;
    body.jumpBufferMs = 0;
    body.coyoteMs = 0;
    body.onGround = false;
  }

  moveX(body, body.vx * dt);
  const landed = moveY(body, body.vy * dt);

  body.onGround = landed;
  body.coyoteMs = landed ? tuning.coyote_ms : Math.max(0, body.coyoteMs - dtMs);
}

function overlaps(x: number, y: number): boolean {
  const size = map.tile_size;
  const left = Math.floor(x / size);
  const right = Math.floor((x + tuning.player_width - 1) / size);
  const top = Math.floor(y / size);
  const bottom = Math.floor((y + tuning.player_height - 1) / size);

  for (let row = top; row <= bottom; row++) {
    for (let col = left; col <= right; col++) {
      if (isSolidTile(col, row)) return true;
    }
  }
  return false;
}

function moveX(body: Body, delta: number): void {
  if (delta === 0) return;
  const target = body.x + delta;
  if (!overlaps(target, body.y)) {
    body.x = target;
    return;
  }

  // A stair is one tile high, so walking into one should climb it rather
  // than stop dead. Only from the ground, so it cannot be used mid-jump.
  if (body.onGround) {
    for (let lift = 1; lift <= tuning.step_height; lift++) {
      if (!overlaps(target, body.y - lift)) {
        body.x = target;
        body.y -= lift;
        return;
      }
    }
  }

  // Walk up to the wall one pixel at a time so the body ends up flush with it.
  const stepPx = Math.sign(delta);
  while (!overlaps(body.x + stepPx, body.y)) {
    body.x += stepPx;
  }
  body.vx = 0;
}

/** Returns true when the move ended with ground under the body. */
function moveY(body: Body, delta: number): boolean {
  if (delta === 0) return body.onGround && !overlaps(body.x, body.y + 1);

  const target = body.y + delta;
  if (!overlaps(body.x, target)) {
    body.y = target;
    return false;
  }

  const stepPx = Math.sign(delta);
  while (!overlaps(body.x, body.y + stepPx)) {
    body.y += stepPx;
  }
  const landedOnFloor = delta > 0;
  body.vy = 0;
  return landedOnFloor;
}
