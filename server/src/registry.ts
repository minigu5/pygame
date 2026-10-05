import { ROOM_CODE } from "./env";
import type { Phase, RoomListing } from "./protocol";

// Rooms report in every 30 seconds; one that has missed three is gone.
const STALE_MS = 90_000;
const PREFIX = "room:";
const PHASES: Phase[] = ["waiting", "hiding", "seeking", "result"];

type Entry = RoomListing & { updatedAt: number };

/** The one list of open rooms. Rooms write to it; the lobby only reads. */
export class RegistryDO implements DurableObject {
  constructor(private state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/rooms" && request.method === "GET") {
      return Response.json(await this.list(), { headers: { "Cache-Control": "no-store" } });
    }
    if (url.pathname === "/room" && request.method === "PUT") {
      const entry = parseEntry(await request.json().catch(() => null));
      if (entry === null) return new Response("bad room", { status: 400 });
      await this.state.storage.put(PREFIX + entry.code, entry);
      return new Response(null, { status: 204 });
    }
    if (url.pathname === "/room" && request.method === "DELETE") {
      // Deleting a room that is not listed is fine: the last player may leave twice over.
      await this.state.storage.delete(PREFIX + (url.searchParams.get("code") ?? ""));
      return new Response(null, { status: 204 });
    }
    return new Response("not found", { status: 404 });
  }

  private async list(): Promise<RoomListing[]> {
    const entries = await this.state.storage.list<Entry>({ prefix: PREFIX });
    const cutoff = Date.now() - STALE_MS;
    const stale: string[] = [];
    const rooms: RoomListing[] = [];
    for (const [key, entry] of entries) {
      // An entry with no timestamp was left by an older build of this object: stale too.
      if (!(entry.updatedAt >= cutoff)) {
        stale.push(key);
        continue;
      }
      const { updatedAt: _, ...listing } = entry;
      rooms.push(listing);
    }
    if (stale.length > 0) await this.state.storage.delete(stale);
    return rooms;
  }
}

function parseEntry(raw: unknown): Entry | null {
  if (typeof raw !== "object" || raw === null) return null;
  const { code, name, players, capacity, phase } = raw as Record<string, unknown>;
  if (typeof code !== "string" || !ROOM_CODE.test(code)) return null;
  if (typeof name !== "string" || name.length > 64) return null;
  if (!Number.isInteger(players) || !Number.isInteger(capacity)) return null;
  if (!PHASES.includes(phase as Phase)) return null;
  return {
    code,
    name,
    players: players as number,
    capacity: capacity as number,
    phase: phase as Phase,
    updatedAt: Date.now(),
  };
}
