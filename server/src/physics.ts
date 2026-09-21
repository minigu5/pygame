import { isSolidTile, map, tuning } from "./map";

export const LEFT = 1;
export const RIGHT = 2;
export const JUMP = 4;

export type Body = {
  x: number;
  y: number;
  vx: number;
  vy: number;
  onGround: boolean;
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
    frozen: false,
    coyoteMs: 0,
    jumpBufferMs: 0,
    jumpHeld: false,
  };
}

/** Advance one body by a single tick. `mask` is this frame's key bitmask. */
export function step(body: Body, mask: number, dtMs: number): void {
  if (body.frozen) {
    body.vx = 0;
    body.vy = 0;
    return;
  }

  const dt = dtMs / 1000;
  const wantsJump = (mask & JUMP) !== 0;

  body.jumpBufferMs = wantsJump && !body.jumpHeld ? tuning.jump_buffer_ms : Math.max(0, body.jumpBufferMs - dtMs);

  // Releasing jump early cuts the rise short, which is what makes the height
  // controllable rather than fixed.
  if (!wantsJump && body.jumpHeld && body.vy < 0) {
    body.vy *= tuning.short_hop_factor;
  }
  body.jumpHeld = wantsJump;

  const direction = ((mask & RIGHT) !== 0 ? 1 : 0) - ((mask & LEFT) !== 0 ? 1 : 0);
  body.vx = direction * tuning.move_speed;

  if (body.jumpBufferMs > 0 && body.coyoteMs > 0) {
    body.vy = tuning.jump_speed;
    body.jumpBufferMs = 0;
    body.coyoteMs = 0;
    body.onGround = false;
  }

  body.vy = Math.min(body.vy + tuning.gravity * dt, tuning.max_fall_speed);

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
