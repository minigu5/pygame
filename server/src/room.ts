import type { ClientMessage, Role, ServerMessage } from "./protocol";
import { TICK_MS } from "./protocol";

type Connection = {
  id: string;
  role: Role;
  socket: WebSocket;
};

export class RoomDO implements DurableObject {
  private connections = new Map<string, Connection>();
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

    const connection: Connection = {
      id: crypto.randomUUID().slice(0, 8),
      role: this.nextRole(),
      socket: server,
    };
    this.connections.set(connection.id, connection);

    server.addEventListener("message", (event) =>
      this.onMessage(connection, event.data),
    );
    server.addEventListener("close", () => this.onClose(connection));
    server.addEventListener("error", () => this.onClose(connection));

    this.send(connection, {
      t: "hello",
      id: connection.id,
      role: connection.role,
      tick: this.tick,
    });
    this.broadcast({ t: "j", id: connection.id, role: connection.role }, connection.id);
    this.startTicking();

    return new Response(null, { status: 101, webSocket: client });
  }

  // First player hunts, second hides, the rest watch.
  private nextRole(): Role {
    const taken = new Set([...this.connections.values()].map((c) => c.role));
    if (!taken.has("hunter")) return "hunter";
    if (!taken.has("chameleon")) return "chameleon";
    return "spectator";
  }

  private onMessage(connection: Connection, raw: unknown): void {
    if (typeof raw !== "string") return;

    let message: ClientMessage;
    try {
      message = JSON.parse(raw) as ClientMessage;
    } catch {
      return;
    }

    if (message.t === "ping") {
      this.send(connection, { t: "pong", ts: message.ts });
    }
  }

  private onClose(connection: Connection): void {
    if (!this.connections.delete(connection.id)) return;
    this.broadcast({ t: "b", id: connection.id });
    if (this.connections.size === 0) this.stopTicking();
  }

  // setInterval rather than the Alarms API: each alarm invocation is a billed
  // request, which a 60Hz loop would exhaust in about a day.
  private startTicking(): void {
    if (this.timer !== null) return;
    this.timer = setInterval(() => {
      this.tick++;
    }, TICK_MS) as unknown as number;
  }

  private stopTicking(): void {
    if (this.timer === null) return;
    clearInterval(this.timer);
    this.timer = null;
  }

  private send(connection: Connection, message: ServerMessage): void {
    connection.socket.send(JSON.stringify(message));
  }

  private broadcast(message: ServerMessage, exceptId?: string): void {
    const payload = JSON.stringify(message);
    for (const connection of this.connections.values()) {
      if (connection.id === exceptId) continue;
      connection.socket.send(payload);
    }
  }
}
