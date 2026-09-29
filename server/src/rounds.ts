import { tuning } from "./map";
import type { Phase, Winner } from "./protocol";

const SECOND = 1000;

export type RoomOptions = {
  hideMs: number;
  seekMs: number;
  resultMs: number;
};

/** Room settings come from the link the first player opens, within limits. */
export function readOptions(url: URL): RoomOptions {
  return {
    hideMs: clampSeconds(url.searchParams.get("hide"), tuning.hide_seconds, 5, 180),
    seekMs: clampSeconds(url.searchParams.get("seek"), tuning.seek_seconds, 10, 600),
    resultMs: clampSeconds(url.searchParams.get("result"), tuning.result_seconds, 2, 30),
  };
}

function clampSeconds(raw: string | null, fallback: number, low: number, high: number): number {
  const parsed = raw === null ? Number.NaN : Number(raw);
  const seconds = Number.isFinite(parsed) ? Math.min(high, Math.max(low, parsed)) : fallback;
  return Math.round(seconds * SECOND);
}

export class RoundClock {
  phase: Phase = "waiting";
  round = 0;
  winner: Winner | undefined;
  private endsAt = 0;

  constructor(private options: RoomOptions) {}

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
