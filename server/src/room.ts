import { map, roomAt, tuning } from "./map";
import { spawnBody, step, type Body } from "./physics";
import type { ClientMessage, Role, ServerMessage } from "./protocol";
import { RoundClock, readOptions, type RoomOptions } from "./rounds";

const TICK_MS = 1000 / tuning.tick_hz;
const SNAPSHOT_EVERY = Math.round(tuning.tick_hz / tuning.snapshot_hz);

// Keep replaying the last input for a moment so a late packet does not read as
// the player letting go of every key.
const INPUT_COAST_TICKS = 8;

const DEFAULT_COLOR: [number, number, number] = [210, 120, 90];

type Player = {
  id: string;
  role: Role;
  socket: WebSocket;
  body: Body;
  color: [number, number, number];
  caught: boolean;
  room: string | null;
  watching: string | null;
  accuseReadyAt: number;
  pending: { n: number; mask: number }[];
  lastMask: number;
  coastTicks: number;
  ackInput: number;
};

export class RoomDO implements DurableObject {
  private players = new Map<string, Player>();
  private order: string[] = [];
  private hunterIndex = 0;
  private options: RoomOptions | null = null;
  private clock = new RoundClock({ hideMs: 0, seekMs: 0, resultMs: 0 });
  private timer: number | null = null;
  private tick = 0;

  constructor(
    private state: DurableObjectState,
    private env: unknown,
  ) {}

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("expected websocket", { status: 426 });
    }

    if (this.options === null) {
      this.options = readOptions(new URL(request.url));
      this.clock = new RoundClock(this.options);
    }

    if (this.players.size >= tuning.max_players) {
      return new Response("room is full", { status: 409 });
    }

    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    server.accept();

    const player: Player = {
      id: crypto.randomUUID().slice(0, 8),
      role: "spectator",
      socket: server,
      body: spawnBody(map.spawn.chameleon),
      color: [...DEFAULT_COLOR],
      caught: false,
      room: null,
      watching: null,
      accuseReadyAt: 0,
      pending: [],
      lastMask: 0,
      coastTicks: 0,
      ackInput: 0,
    };
    this.players.set(player.id, player);
    this.order.push(player.id);

    server.addEventListener("message", (event) => this.onMessage(player, event.data));
    server.addEventListener("close", () => this.onClose(player));
    server.addEventListener("error", () => this.onClose(player));

    this.send(player, {
      t: "hello",
      id: player.id,
      role: player.role,
      tick: this.tick,
      map: "map_01",
    });
    this.broadcast({ t: "j", id: player.id, role: player.role }, player.id);
    this.startTicking();
    // A round needs someone to hide from, so one player waits for another.
    if (this.clock.phase === "waiting" && this.players.size >= 2) this.startRound();

    return new Response(null, { status: 101, webSocket: client });
  }

  /** Deal roles for a round: one hunter, everyone else hides. */
  private startRound(): void {
    this.clock.startRound();
    const ids = this.order.filter((id) => this.players.has(id));
    this.order = ids;
    if (ids.length === 0) return;

    const hunterId = ids[this.hunterIndex % ids.length];
    for (const id of ids) {
      const player = this.players.get(id)!;
      player.role = id === hunterId ? "hunter" : "chameleon";
      player.caught = false;
      player.watching = null;
      player.accuseReadyAt = 0;
      player.pending = [];
      player.lastMask = 0;
      player.body = spawnBody(map.spawn[player.role] ?? map.spawn.chameleon);
      // Spread the hiders out so they do not all start on one tile.
      if (player.role === "chameleon") {
        player.body.x += ids.indexOf(id) * tuning.player_width * 3;
      }
    }
  }

  private endRound(winner: "hunter" | "chameleons"): void {
    this.clock.finish(winner);
    for (const player of this.players.values()) player.body.frozen = true;
  }

  private livingChameleons(): number {
    let count = 0;
    for (const player of this.players.values()) {
      if (player.role === "chameleon" && !player.caught) count++;
    }
    return count;
  }

  private onMessage(player: Player, raw: unknown): void {
    if (typeof raw !== "string") return;

    let message: ClientMessage;
    try {
      message = JSON.parse(raw) as ClientMessage;
    } catch {
      return;
    }

    switch (message.t) {
      case "ping":
        this.send(player, { t: "pong", ts: message.ts });
        break;
      case "f":
        if (player.role !== "chameleon") break;
        player.body.frozen = message.v;
        break;
      case "p": {
        if (player.role !== "chameleon") break;
        const channels = message.c;
        if (!Array.isArray(channels) || channels.length !== 3) break;
        player.color = channels.map((value) =>
          Math.max(0, Math.min(255, Math.round(value))),
        ) as [number, number, number];
        break;
      }
      case "a": {
        if (player.role !== "hunter" || this.clock.phase !== "seeking") break;
        const now = Date.now();
        if (now < player.accuseReadyAt) break;
        const hit = this.chameleonAt(message.x, message.y);
        if (hit) {
          hit.caught = true;
          hit.body.frozen = true;
          hit.watching = player.id;
          this.broadcast({ t: "c", id: hit.id, by: player.id });
          if (this.livingChameleons() === 0) this.endRound("hunter");
        } else {
          player.accuseReadyAt = now + tuning.accuse_cooldown_ms;
          this.send(player, { t: "cd", until: player.accuseReadyAt });
        }
        break;
      }
      case "i": {
        if (player.role === "spectator") break;
        // message.n numbers the first frame in the batch; the client replays
        // everything after the frame the snapshot acknowledges.
        message.k.forEach((mask, index) =>
          player.pending.push({ n: message.n + index, mask: mask & 31 }),
        );
        break;
      }
    }
  }

  private onClose(player: Player): void {
    if (!this.players.delete(player.id)) return;
    this.order = this.order.filter((id) => id !== player.id);
    this.broadcast({ t: "b", id: player.id });

    if (this.players.size === 0) {
      this.stopTicking();
      this.clock.wait();
      return;
    }
    // A round with nobody left to find, or nobody to find them, is over.
    if (this.clock.phase !== "waiting" && (this.players.size < 2 || this.livingChameleons() === 0)) {
      this.clock.wait();
    }
  }

  // setInterval rather than the Alarms API: each alarm invocation is a billed
  // request, which a 60Hz loop would exhaust in about a day.
  private startTicking(): void {
    if (this.timer !== null) return;
    this.timer = setInterval(() => this.onTick(), TICK_MS) as unknown as number;
  }

  private stopTicking(): void {
    if (this.timer === null) return;
    clearInterval(this.timer);
    this.timer = null;
    this.tick = 0;
  }

  private onTick(): void {
    this.tick++;
    this.advanceRound();

    const hunterWaits = this.clock.phase === "hiding";
    for (const player of this.players.values()) {
      if (player.role === "spectator" || player.caught) continue;

      const next = player.pending.shift();
      if (next === undefined) {
        player.coastTicks++;
        if (player.coastTicks > INPUT_COAST_TICKS) player.lastMask = 0;
      } else {
        player.lastMask = next.mask;
        player.ackInput = next.n;
        player.coastTicks = 0;
      }

      // The hunter is shut out while the others hide, and nobody moves once
      // the round is decided.
      const held =
        this.clock.phase === "result" || (hunterWaits && player.role === "hunter");
      step(player.body, held ? 0 : player.lastMask, TICK_MS);
      player.room = roomAt(
        player.body.x + tuning.player_width / 2,
        player.body.y + tuning.player_height / 2,
      );
    }

    if (this.tick % SNAPSHOT_EVERY === 0) this.sendSnapshots();
  }

  private advanceRound(): void {
    if (!this.clock.expired()) return;

    switch (this.clock.phase) {
      case "hiding":
        this.clock.startSeeking();
        break;
      case "seeking":
        // Time ran out with someone still hidden, so the hiders win.
        this.endRound("chameleons");
        break;
      case "result":
        if (this.players.size >= 2) {
          this.hunterIndex++;
          this.startRound();
        } else {
          this.clock.wait();
        }
        break;
    }
  }

  /** The chameleon whose body covers the accused point, if any. */
  private chameleonAt(x: number, y: number): Player | null {
    const radius = tuning.accuse_radius;
    for (const player of this.players.values()) {
      if (player.caught || player.role !== "chameleon") continue;
      const centreX = player.body.x + tuning.player_width / 2;
      const centreY = player.body.y + tuning.player_height / 2;
      const halfWidth = tuning.player_width / 2 + radius;
      const halfHeight = tuning.player_height / 2 + radius;
      if (Math.abs(x - centreX) <= halfWidth && Math.abs(y - centreY) <= halfHeight) {
        return player;
      }
    }
    return null;
  }

  /** Whose eyes a client sees through: its own, or the hunter it watches. */
  private viewpoint(player: Player): Player {
    if (player.watching === null) return player;
    return this.players.get(player.watching) ?? player;
  }

  private sendSnapshots(): void {
    for (const player of this.players.values()) {
      const eyes = this.viewpoint(player);
      const others = [];
      for (const other of this.players.values()) {
        if (other.id === eyes.id || other.caught) continue;
        // Filtering by room, not by viewport: a player in another room is
        // never sent, so a modified client cannot reveal one.
        if (other.room !== eyes.room) continue;
        others.push({
          i: other.id,
          x: Math.round(other.body.x),
          y: Math.round(other.body.y),
          fz: other.body.frozen,
          c: other.color,
        });
      }

      this.send(player, {
        t: "s",
        n: player.ackInput,
        ph: this.clock.phase,
        left: this.clock.secondsLeft,
        rd: this.clock.round,
        ...(this.clock.winner ? { win: this.clock.winner } : {}),
        me: {
          x: Math.round(eyes.body.x),
          y: Math.round(eyes.body.y),
          vy: Math.round(eyes.body.vy),
          g: eyes.body.onGround,
          fz: eyes.body.frozen,
          rm: eyes.room,
          rl: player.role,
          ct: player.caught,
          c: eyes.color,
        },
        o: others,
      });
    }
  }

  private send(player: Player, message: ServerMessage): void {
    player.socket.send(JSON.stringify(message));
  }

  private broadcast(message: ServerMessage, exceptId?: string): void {
    const payload = JSON.stringify(message);
    for (const player of this.players.values()) {
      if (player.id === exceptId) continue;
      player.socket.send(payload);
    }
  }
}
