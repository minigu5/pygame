export type Role = "hunter" | "chameleon" | "spectator";

export type ClientMessage =
  | { t: "ping"; ts: number }
  | { t: "i"; n: number; k: number[] }
  | { t: "f"; v: boolean }
  | { t: "p"; c: [number, number, number] }
  | { t: "a"; x: number; y: number };

export type ServerMessage =
  | { t: "pong"; ts: number }
  | { t: "hello"; id: string; role: Role; tick: number }
  | { t: "j"; id: string; role: Role }
  | { t: "b"; id: string };

export const TICK_HZ = 60;
export const TICK_MS = 1000 / TICK_HZ;
