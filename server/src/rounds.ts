import { map, tuning } from "./map";
import type { Phase, Winner } from "./protocol";

const SECOND = 1000;
const LIMITS = tuning.room_limits;

export type RoomOptions = {
  name: string;
  maxPlayers: number;
  hideMs: number;
  seekMs: number;
  resultMs: number;
  background: string;   // an id from the map's backgrounds
};

/** What the host may change from the waiting room; seconds, as the client shows them. */
export type RoomChanges = {
  name?: unknown;
  max?: unknown;
  hide?: unknown;
  seek?: unknown;
  result?: unknown;
  bg?: unknown;
};

/** Room settings start from the link the first player opens, within limits. */
export function readOptions(url: URL, code: string): RoomOptions {
  const params = url.searchParams;
  return {
    name: cleanName(params.get("name")) ?? code,
    maxPlayers: clamp(params.get("max"), tuning.max_players, LIMITS.players),
    hideMs: clamp(params.get("hide"), tuning.hide_seconds, LIMITS.hide) * SECOND,
    seekMs: clamp(params.get("seek"), tuning.seek_seconds, LIMITS.seek) * SECOND,
    resultMs: clamp(params.get("result"), tuning.result_seconds, LIMITS.result) * SECOND,
    background: knownBackground(params.get("bg")) ?? map.backgrounds[0].id,
  };
}

/** Applies the host's changes in place; anything missing or malformed is left as it was. */
export function applyChanges(options: RoomOptions, changes: RoomChanges, playersNow: number): void {
  options.name = cleanName(changes.name) ?? options.name;
  // The room cannot shrink below the people already in it.
  options.maxPlayers = Math.max(
    playersNow,
    clamp(changes.max, options.maxPlayers, LIMITS.players),
  );
  options.hideMs = clamp(changes.hide, options.hideMs / SECOND, LIMITS.hide) * SECOND;
  options.seekMs = clamp(changes.seek, options.seekMs / SECOND, LIMITS.seek) * SECOND;
  options.resultMs = clamp(changes.result, options.resultMs / SECOND, LIMITS.result) * SECOND;
  options.background = knownBackground(changes.bg) ?? options.background;
}

/** A background for the next round: any of the map's but the one just played in. */
export function otherBackground(current: string): string {
  const others = map.backgrounds.filter((background) => background.id !== current);
  if (others.length === 0) return current;
  return others[Math.floor(Math.random() * others.length)].id;
}

function knownBackground(raw: unknown): string | null {
  return map.backgrounds.some((background) => background.id === raw) ? (raw as string) : null;
}

function clamp(raw: unknown, fallback: number, [low, high]: number[]): number {
  const parsed = raw === null || raw === undefined || raw === "" ? Number.NaN : Number(raw);
  return Number.isFinite(parsed) ? Math.round(Math.min(high, Math.max(low, parsed))) : fallback;
}

/** A display name: one line, trimmed, no control characters; null when nothing is left. */
function cleanName(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const name = [...raw.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim()]
    .slice(0, LIMITS.name)
    .join("")
    .trim();
  return name === "" ? null : name;
}

export class RoundClock {
  phase: Phase = "waiting";
  round = 0;
  winner: Winner | undefined;
  private endsAt = 0;

  // The lengths are read when a phase begins, so what the host changes in the
  // waiting room applies to the next round.
  constructor(private options: Pick<RoomOptions, "hideMs" | "seekMs" | "resultMs">) {}

  get secondsLeft(): number {
    if (this.phase === "waiting") return 0;
    return Math.max(0, Math.ceil((this.endsAt - Date.now()) / SECOND));
  }

  expired(): boolean {
    return this.phase !== "waiting" && Date.now() >= this.endsAt;
  }

  wait(): void {
    this.phase = "waiting";
    this.winner = undefined;
    this.endsAt = 0;
  }

  startRound(): void {
    this.round++;
    this.winner = undefined;
    this.enter("hiding", this.options.hideMs);
  }

  startSeeking(): void {
    this.enter("seeking", this.options.seekMs);
  }

  finish(winner: Winner): void {
    this.winner = winner;
    this.enter("result", this.options.resultMs);
  }

  private enter(phase: Phase, durationMs: number): void {
    this.phase = phase;
    this.endsAt = Date.now() + durationMs;
  }
}
