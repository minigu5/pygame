export type Role = "hunter" | "chameleon" | "spectator";

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

export type ServerMessage =
  | { t: "pong"; ts: number }
  | { t: "hello"; id: string; role: Role; tick: number; map: string }
  | { t: "j"; id: string; role: Role }
  | { t: "b"; id: string }
  | {
      t: "s";
      n: number;
      me: {
        x: number;
        y: number;
        vy: number;
        g: boolean;
        fz: boolean;
        rm: string | null;
        c: [number, number, number];
      };
      o: PlayerView[];
    };
