export { RoomDO } from "./room";

type Env = {
  ROOM: DurableObjectNamespace;
};

const ROOM_CODE = /^[a-z0-9-]{1,32}$/;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return new Response("ok");
    }

    if (url.pathname === "/ws") {
      const code = url.searchParams.get("room");
      if (!code || !ROOM_CODE.test(code)) {
        return new Response("bad room code", { status: 400 });
      }
      const id = env.ROOM.idFromName(code);
      return env.ROOM.get(id).fetch(request);
    }

    return new Response("not found", { status: 404 });
  },
};
