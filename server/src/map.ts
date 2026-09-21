import mapData from "../../shared/map_test.json";
import tuningData from "../../shared/tuning.json";

export type PaletteEntry = {
  name: string;
  color: [number, number, number] | null;
  solid: boolean;
};

export type Room = {
  id: string;
  name: string;
  floor: number;
  rect: [number, number, number, number];
  stairs?: boolean;
};

export type GameMap = {
  tile_size: number;
  size: [number, number];
  palette: PaletteEntry[];
  bg: number[][];
  solid: number[][];
  fg: number[][];
  rooms: Room[];
  spawn: Record<string, [number, number]>;
};

export type Tuning = typeof tuningData;

export const map = mapData as unknown as GameMap;
export const tuning: Tuning = tuningData;

const solidByIndex = map.palette.map((entry) => entry.solid);

export function isSolidTile(col: number, row: number): boolean {
  const [width, height] = map.size;
  if (col < 0 || row < 0 || col >= width || row >= height) return true;
  return solidByIndex[map.solid[row][col]] ?? false;
}

// The room whose rect contains the point, or null in the gaps between rooms.
export function roomAt(x: number, y: number): string | null {
  const size = map.tile_size;
  const col = Math.floor(x / size);
  const row = Math.floor(y / size);
  for (const room of map.rooms) {
    const [rx, ry, rw, rh] = room.rect;
    if (col >= rx && col < rx + rw && row >= ry && row < ry + rh) return room.id;
  }
  return null;
}
