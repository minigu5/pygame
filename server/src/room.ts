import type { Env } from "./env";
import { map, roomAt, tuning } from "./map";
import { spawnBody, step, type Body } from "./physics";
import type { ClientMessage, Role, RoomListing, ServerMessage } from "./protocol";
import { RoundClock, applyChanges, readOptions, type RoomOptions } from "./rounds";

const TICK_MS = 1000 / tuning.tick_hz;
const SNAPSHOT_EVERY = Math.round(tuning.tick_hz / tuning.snapshot_hz);

// Keep replaying the last input for a moment so a late packet does not read as
// the player letting go of every key.
const INPUT_COAST_TICKS = 8;
// A timer that fires late is made up for by running the missed ticks at once,
// up to this many, so the simulation keeps wall-clock time.
const MAX_CATCHUP_TICKS = 8;
// Inputs queued beyond this are drained two per tick: a client ahead of the
// server would otherwise fall further behind every second, and a freeze
// pressed now would land where the body was long ago.
const MAX_INPUT_BACKLOG = 6;
// How often a room with players tells the lobby list it is still there.
const HEARTBEAT_TICKS = 30 * tuning.tick_hz;
// Hiders are dealt out leftwards from here, so a full room still fits between the walls.
const HIDER_SPAWN_LEAD = tuning.player_width * 3;
const HIDER_SPAWN_GAP = tuning.player_width * 2;

const DEFAULT_COLOR: [number, number, number] = [210, 120, 90];
// A 96x128 painting packed by the client is 50 KB at its very worst.
const MAX_ART_CHARS = 64_000;
const POSES = 3;

// Whole pixels would put a body resting at y=112.6 a pixel into the floor on
// the client, which then nudges it back up: a tenth keeps snapshots short
// without that bob.
function tenths(value: number): number {
  return Math.round(value * 10) / 10;
}

type Player = {
  id: string;
  role: Role;
  socket: WebSocket;
  body: Body;
  color: [number, number, number];
  // The painting on the body, and how many times it has changed.
  art: string | null;
  artVersion: number;
  // Which version of each other player's painting this client has been sent.
  artSeen: Map<string, number>;
  pose: number;
  caught: boolean;
  room: string | null;
  watching: string | null;
  accuseReadyAt: number;
  pending: PendingInput[];
  // A freeze toggle for an input frame that has not been queued yet.
  freezeAt: { n: number; v: boolean } | null;
  lastMask: number;
  coastTicks: number;
  ackInput: number;
};

type PendingInput = { n: number; mask: number; freeze?: boolean };

export class RoomDO implements DurableObject {
  private players = new Map<string, Player>();
  private order: string[] = [];
  private hunterIndex = 0;
  private code = "";
  private options: RoomOptions = {
    name: "",
    maxPlayers: tuning.max_players,
    hideMs: 0,
    seekMs: 0,
    resultMs: 0,
    background: map.backgrounds[0].id,
  };
  private clock = new RoundClock(this.options);
  private timer: number | null = null;
  private tick = 0;
  private tickDue = 0;   // wall-clock time the next tick is owed at
  private listing: Promise<void> = Promise.resolve();
  private listingQueued = false;

  constructor(
    private state: DurableObjectState,
    private env: Env,
  ) {}

  async fetch(request: Request): Promise<Response> {
    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("expected websocket", { status: 426 });
    }

    if (this.players.size === 0) {
      // Whoever walks into an empty room opens it afresh, with their settings.
      const url = new URL(request.url);
      this.code = url.searchParams.get("room") ?? "";
      this.options = readOptions(url, this.code);
      this.clock = new RoundClock(this.options);
      this.hunterIndex = 0;
    }

    if (this.players.size >= this.options.maxPlayers) {
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
      art: null,
      artVersion: 0,
      artSeen: new Map(),
      pose: 0,
      caught: false,
      room: null,
      watching: null,
      accuseReadyAt: 0,
      pending: [],
      freezeAt: null,
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
    // The room waits until its host starts the round; see "start" below.
    this.broadcastRoomInfo();
    this.publish();

    return new Response(null, { status: 101, webSocket: client });
  }

  /** The player who may start the round and change the settings: whoever has been here longest. */
  private get hostId(): string {
    return this.order[0] ?? "";
  }

  private broadcastRoomInfo(): void {
    this.broadcast({
      t: "r",
      code: this.code,
      name: this.options.name,
      host: this.hostId,
      n: this.players.size,
      max: this.options.maxPlayers,
      hide: this.options.hideMs / 1000,
      seek: this.options.seekMs / 1000,
      result: this.options.resultMs / 1000,
      bg: this.options.background,
    });
  }

  /** Tell the lobby list how this room stands now. Never in the way of the game:
   * updates go out one at a time, each reading the room as it is when sent, so
   * a late one cannot put back a room that has since emptied. */
  private publish(): void {
    if (this.listingQueued) return;
    this.listingQueued = true;
    this.listing = this.listing.then(async () => {
      this.listingQueued = false;
      try {
        const registry = this.env.REGISTRY.get(this.env.REGISTRY.idFromName("rooms"));
        if (this.players.size === 0) {
          await registry.fetch(`https://registry/room?code=${this.code}`, { method: "DELETE" });
          return;
        }
        const listing: RoomListing = {
          code: this.code,
          name: this.options.name,
          players: this.players.size,
          capacity: this.options.maxPlayers,
          phase: this.clock.phase,
        };
        await registry.fetch("https://registry/room", {
          method: "PUT",
          body: JSON.stringify(listing),
        });
      } catch {
        // A room missing from the list is still a room: play goes on.
      }
    });
    this.state.waitUntil(this.listing);
  }

  /** Back to the waiting room: nobody has a role until the host starts again. */
  private toWaiting(): void {
    this.clock.wait();
    for (const player of this.players.values()) {
      player.role = "spectator";
      player.art = null;
      player.pose = 0;
      player.caught = false;
      player.watching = null;
      player.pending = [];
      player.freezeAt = null;
      player.lastMask = 0;
      player.body = spawnBody(map.spawn.chameleon);
      player.room = null;
    }
    this.publish();
  }

  /** Deal roles for a round: one hunter, everyone else hides. */
  private startRound(): void {
    this.clock.startRound();
    this.publish();
    const ids = this.order.filter((id) => this.players.has(id));
    this.order = ids;
    if (ids.length === 0) return;

    const hunterId = ids[this.hunterIndex % ids.length];
    let hiders = 0;
    for (const id of ids) {
      const player = this.players.get(id)!;
      player.role = id === hunterId ? "hunter" : "chameleon";
      // Each round is painted afresh; the clients send theirs again.
      player.art = null;
      player.pose = 0;
      player.caught = false;
      player.watching = null;
      player.accuseReadyAt = 0;
      player.pending = [];
      player.freezeAt = null;
      player.lastMask = 0;
      player.body = spawnBody(map.spawn[player.role] ?? map.spawn.chameleon);
      // Spread the hiders out so they do not all start on one tile.
      if (player.role === "chameleon") {
        player.body.x += HIDER_SPAWN_LEAD - hiders * HIDER_SPAWN_GAP;
        hiders++;
      }
    }
  }

  private endRound(winner: "hunter" | "chameleons"): void {
    this.clock.finish(winner);
    this.publish();
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
      case "f": {
        if (player.role !== "chameleon") break;
        const n = message.n;
        if (typeof n !== "number" || n <= player.ackInput) {
          // An old client, or a frame already played: now is the best we can do.
          player.body.frozen = message.v;
          break;
        }
        const queued = player.pending.find((input) => input.n === n);
        if (queued) queued.freeze = message.v;
        else player.freezeAt = { n, v: message.v };
        break;
      }
      case "p": {
        if (player.role !== "chameleon") break;
        const channels = message.c;
        if (!Array.isArray(channels) || channels.length !== 3) break;
        player.color = channels.map((value) =>
          Math.max(0, Math.min(255, Math.round(value))),
        ) as [number, number, number];
        break;
      }
      case "art": {
        if (player.role !== "chameleon") break;
        if (typeof message.d !== "string" || message.d.length > MAX_ART_CHARS) break;
        player.art = message.d;
        player.artVersion++;
        break;
      }
      case "ps": {
        if (player.role !== "chameleon") break;
        if (Number.isInteger(message.v) && message.v >= 0 && message.v < POSES) {
          player.pose = message.v;
        }
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
      case "start":
        // A round needs someone to hide from.
        if (player.id !== this.hostId || this.clock.phase !== "waiting") break;
        if (this.players.size < 2) break;
        this.startRound();
        break;
      case "cfg":
        if (player.id !== this.hostId || this.clock.phase !== "waiting") break;
        applyChanges(this.options, message, this.players.size);
        this.broadcastRoomInfo();
        this.publish();
        break;
      case "i": {
        // A body that is not being stepped would only queue these up unread.
        if (player.role === "spectator" || player.caught) break;
        // message.n numbers the first frame in the batch; the client replays
        // everything after the frame the snapshot acknowledges.
        message.k.forEach((mask, index) => {
          const input: PendingInput = { n: message.n + index, mask: mask & 31 };
          if (player.freezeAt !== null && player.freezeAt.n === input.n) {
            input.freeze = player.freezeAt.v;
            player.freezeAt = null;
          }
          player.pending.push(input);
        });
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
      this.publish();
      return;
    }
    // The host may have been the one to go: the next longest here takes over.
    this.broadcastRoomInfo();
    this.publish();

    if (this.clock.phase === "waiting") return;
    if (this.players.size < 2) {
      this.toWaiting();
    } else if (this.clock.phase !== "result") {
      // A round with nobody left to look, or nobody left to find, is decided.
      if (player.role === "hunter") this.endRound("chameleons");
      else if (this.livingChameleons() === 0) this.endRound("hunter");
    }
  }

  // setInterval rather than the Alarms API: each alarm invocation is a billed
  // request, which a 60Hz loop would exhaust in about a day.
  private startTicking(): void {
    if (this.timer !== null) return;
    this.tickDue = Date.now() + TICK_MS;
    this.timer = setInterval(() => this.onTimer(), TICK_MS) as unknown as number;
  }

  private stopTicking(): void {
    if (this.timer === null) return;
    clearInterval(this.timer);
    this.timer = null;
    this.tick = 0;
  }

  // The interval is not trusted to fire on time: every tick owed since the
  // last one is run now, so a slow timer thins the ticks out rather than
  // slowing the game down and letting the input queues pile up.
  private onTimer(): void {
    const now = Date.now();
    let ticks = 0;
    while (this.tickDue <= now && ticks < MAX_CATCHUP_TICKS) {
      this.onTick();
      this.tickDue += TICK_MS;
      ticks++;
    }
    if (this.tickDue <= now) this.tickDue = now + TICK_MS;   // too far behind: drop the rest
  }

  private onTick(): void {
    this.tick++;
    this.advanceRound();
    if (this.tick % HEARTBEAT_TICKS === 0) this.publish();

    const hunterWaits = this.clock.phase === "hiding";
    for (const player of this.players.values()) {
      if (player.role === "spectator" || player.caught) continue;

      // The hunter is shut out while the others hide, and nobody moves once
      // the round is decided.
      const held =
        this.clock.phase === "result" || (hunterWaits && player.role === "hunter");
      const steps = player.pending.length > MAX_INPUT_BACKLOG ? 2 : 1;
      for (let i = 0; i < steps; i++) {
        const next = player.pending.shift();
        if (next === undefined) {
          player.coastTicks++;
          if (player.coastTicks > INPUT_COAST_TICKS) player.lastMask = 0;
        } else {
          player.lastMask = next.mask;
          player.ackInput = next.n;
          player.coastTicks = 0;
          if (next.freeze !== undefined && player.role === "chameleon") {
            player.body.frozen = next.freeze;
          }
        }
        step(player.body, held ? 0 : player.lastMask, TICK_MS);
      }
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
        this.publish();
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
          this.toWaiting();
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
      // Everyone shares the one room, so no wall keeps the hunter from
      // watching the others hide: it is sent nobody until the seeking starts.
      const blind = this.clock.phase === "hiding" && eyes.role === "hunter";
      const others = [];
      for (const other of this.players.values()) {
        if (other.id === eyes.id || other.caught || blind) continue;
        // Filtering by room, not by viewport: a player in another room is
        // never sent, so a modified client cannot reveal one.
        if (other.room !== eyes.room) continue;
        // The painting goes the same way, and only when it has changed: it
        // says which room its owner means to hide in.
        if (other.art !== null && player.artSeen.get(other.id) !== other.artVersion) {
          player.artSeen.set(other.id, other.artVersion);
          this.send(player, { t: "art", id: other.id, d: other.art });
        }
        others.push({
          i: other.id,
          x: tenths(other.body.x),
          y: tenths(other.body.y),
          fz: other.body.frozen,
          c: other.color,
          // A pose is held only while frozen.
          ps: other.body.frozen ? other.pose : 0,
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
          x: tenths(eyes.body.x),
          y: tenths(eyes.body.y),
          vy: tenths(eyes.body.vy),
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
