export type Role = "hunter" | "chameleon" | "spectator";
export type Phase = "waiting" | "hiding" | "seeking" | "result";
export type Winner = "hunter" | "chameleons";

export type ClientMessage =
  | { t: "ping"; ts: number }
  | { t: "i"; n: number; k: number[] }
  | { t: "f"; v: boolean }
  | { t: "p"; c: [number, number, number] }
  | { t: "a"; x: number; y: number };

export type PlayerView = {
  i: string;
  x: number;
  y: number;
  fz: boolean;
  c: [number, number, number];
};

export type Snapshot = {
  t: "s";
  n: number;
  ph: Phase;
  left: number;        // seconds remaining in this phase
  rd: number;          // round number, counting from one
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

export type ServerMessage =
  | { t: "pong"; ts: number }
  | { t: "hello"; id: string; role: Role; tick: number; map: string }
  | { t: "j"; id: string; role: Role }
  | { t: "b"; id: string }
  | { t: "c"; id: string; by: string }
  | { t: "cd"; until: number }
  | Snapshot;
