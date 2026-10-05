export type Role = "hunter" | "chameleon" | "spectator";
export type Phase = "waiting" | "hiding" | "seeking" | "result";
export type Winner = "hunter" | "chameleons";

export type ClientMessage =
  | { t: "ping"; ts: number }
  | { t: "i"; n: number; k: number[] }
  // n: the first input frame the toggle applies to, so it lands on the same
  // frame the client froze on however far behind the input queue is.
  | { t: "f"; v: boolean; n?: number }
  | { t: "p"; c: [number, number, number] }
  | { t: "a"; x: number; y: number }
  // The chameleon's whole painting, as the client packs it (see client/body_art.py).
  // The server does not look inside; it hands it to whoever can see the body.
  | { t: "art"; d: string }
  // The pose a frozen chameleon holds: 0 standing, 1 crouching, 2 lying. Looks only.
  | { t: "ps"; v: number }
  // Host only, while the room waits: deal the first round.
  | { t: "start" }
  // Host only, while the room waits: any subset of the room's settings.
  | { t: "cfg"; name?: string; max?: number; hide?: number; seek?: number; result?: number; bg?: string };

export type PlayerView = {
  i: string;
  x: number;
  y: number;
  fz: boolean;
  c: [number, number, number];
  ps: number;
};

export type Snapshot = {
  t: "s";
  n: number;
  ph: Phase;
  left: number;        // seconds remaining in this phase
  rd: number;          // round number, counting from one
  ml: number;          // wrong accusations the hunter may still make this round
  win?: Winner;
  me: {
    x: number;
    y: number;
    vy: number;
    g: boolean;
    fz: boolean;
    rm: string | null;
    rl: Role;
    ct: boolean;
    c: [number, number, number];
  };
  o: PlayerView[];
};

// The waiting room: sent on joining and whenever any of it changes.
export type RoomInfo = {
  t: "r";
  code: string;
  name: string;
  host: string;        // id of the player who may start and change settings
  n: number;           // players connected
  max: number;
  hide: number;        // phase lengths in seconds
  seek: number;
  result: number;
  bg: string;          // the room's background, an id from the map's backgrounds
};

// What the lobby lists. No ids, positions or colours: nothing that says where anyone is.
export type RoomListing = {
  code: string;
  name: string;
  players: number;
  capacity: number;
  phase: Phase;
};

export type ServerMessage =
  | { t: "pong"; ts: number }
  | RoomInfo
  | { t: "hello"; id: string; role: Role; tick: number; map: string }
  | { t: "j"; id: string; role: Role }
  | { t: "b"; id: string }
  | { t: "c"; id: string; by: string }
  | { t: "cd"; until: number; left: number }
  | { t: "art"; id: string; d: string }
  | Snapshot;
