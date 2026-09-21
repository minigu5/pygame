import { map, roomAt, tuning } from "./map";
import { spawnBody, step, type Body } from "./physics";
import type { ClientMessage, Role, ServerMessage } from "./protocol";

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

    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    server.accept();

    const role = this.nextRole();
    const player: Player = {
      id: crypto.randomUUID().slice(0, 8),
      role,
      socket: server,
      body: spawnBody(map.spawn[role] ?? map.spawn.hunter),
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

    return new Response(null, { status: 101, webSocket: client });
  }

  // First player hunts, second hides, the rest watch.
  private nextRole(): Role {
    const taken = new Set([...this.players.values()].map((p) => p.role));
    if (!taken.has("hunter")) return "hunter";
    if (!taken.has("chameleon")) return "chameleon";
    return "spectator";
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
        if (player.role !== "hunter" || player.caught) break;
        const now = Date.now();
        if (now < player.accuseReadyAt) break;
        const hit = this.chameleonAt(message.x, message.y);
        if (hit) {
          hit.caught = true;
          hit.body.frozen = true;
          hit.role = "spectator";
          hit.watching = player.id;
          this.broadcast({ t: "c", id: hit.id, by: player.id });
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
    this.broadcast({ t: "b", id: player.id });
    if (this.players.size === 0) this.stopTicking();
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

    for (const player of this.players.values()) {
      if (player.role === "spectator") continue;

      const next = player.pending.shift();
      if (next === undefined) {
        player.coastTicks++;
        if (player.coastTicks > INPUT_COAST_TICKS) player.lastMask = 0;
      } else {
        player.lastMask = next.mask;
        player.ackInput = next.n;
        player.coastTicks = 0;
      }

      step(player.body, player.lastMask, TICK_MS);
      player.room = roomAt(
        player.body.x + tuning.player_width / 2,
        player.body.y + tuning.player_height / 2,
      );
    }

    if (this.tick % SNAPSHOT_EVERY === 0) this.sendSnapshots();
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
    if (player.role !== "spectator" || player.watching === null) return player;
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
        me: {
          x: Math.round(eyes.body.x),
          y: Math.round(eyes.body.y),
          vy: Math.round(eyes.body.vy),
          g: eyes.body.onGround,
          fz: eyes.body.frozen,
          rm: eyes.room,
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
