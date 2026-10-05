"""Check that a hunter sees the body a chameleon actually painted.

The painting and the pose travel through the server to whoever can see the
body, and to nobody else: a painting says where its owner means to hide, so
it must not reach the hunter while the hiding is still going on.

Run `npm run dev --prefix server` first, then:
    .venv/bin/python tools/check_paint_sync.py [ws://127.0.0.1:8787]
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import pygame  # noqa: E402
from websockets.asyncio.client import connect  # noqa: E402

import body_shape  # noqa: E402
from body_art import ArtBook, pack, unpack  # noqa: E402
from body_canvas import BodyCanvas  # noqa: E402

RIGHT = 2
BASE_COLOR = (210, 120, 90)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


class Player:
    """A socket that keeps the newest snapshot and every painting it is sent."""

    def __init__(self, socket) -> None:
        self.socket = socket
        self.id = ""
        self.snapshot: dict | None = None
        self.art: list[dict] = []
        self._frame = 1
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            async for raw in self.socket:
                message = json.loads(raw)
                if message["t"] == "hello":
                    self.id = message["id"]
                elif message["t"] == "s":
                    self.snapshot = message
                elif message["t"] == "art":
                    self.art.append(message)
        except Exception:
            pass

    async def send(self, message: dict) -> None:
        await self.socket.send(json.dumps(message))

    async def until(self, wanted, timeout: float = 20.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.snapshot is not None and wanted(self.snapshot):
                return self.snapshot
            await asyncio.sleep(0.02)
        raise TimeoutError("the snapshot waited for never came")

    async def hold(self, mask: int, batches: int) -> None:
        for _ in range(batches):
            await self.send({"t": "i", "n": self._frame, "k": [mask] * 4})
            self._frame += 4
            await asyncio.sleep(4 / 60)


def colours(surface: pygame.Surface) -> bytes:
    return pygame.image.tobytes(surface, "RGB")


async def main(base: str) -> int:
    pygame.init()

    # --- packing ---------------------------------------------------------------
    canvas = BodyCanvas(BASE_COLOR)
    plain = pack(canvas.extended())
    check("an unpainted body packs to almost nothing", len(plain) < 200, f"{len(plain)} characters")
    canvas.line((20, 20), (70, 100), 9, 9, (30, 160, 220))
    canvas.line((70, 20), (20, 100), 5, 5, (240, 230, 60))
    packed = pack(canvas.extended())
    check("a painted one stays small enough to send", len(packed) < 16000, f"{len(packed)} characters")
    restored = unpack(packed)
    check(
        "and unpacks to the same painting",
        restored is not None and colours(restored) == colours(canvas.extended()),
    )
    check(
        "anything that is not a painting is turned away",
        unpack("not base64!") is None and unpack(packed[: len(packed) // 2]) is None and unpack("") is None,
    )

    # --- through the server ----------------------------------------------------
    room = f"paint-{int(time.time())}"
    async with connect(f"{base}/ws?room={room}&hide=5&seek=600") as first, connect(f"{base}/ws?room={room}") as second:
        hunter, hider = Player(first), Player(second)
        await hunter.until(lambda s: True)
        await hider.until(lambda s: True)
        await hunter.send({"t": "start"})
        await hider.until(lambda s: s["ph"] == "hiding")

        await hider.send({"t": "art", "d": packed})
        await hunter.send({"t": "art", "d": packed})
        await asyncio.sleep(1.0)
        blind = hunter.snapshot
        check(
            "the hunter is shown nobody while the others hide",
            blind["ph"] == "hiding" and blind["o"] == [],
            f"{blind['ph']}, sees {len(blind['o'])}",
        )
        check(
            "nor is it sent a painting yet",
            hunter.art == [],
            f"{len(hunter.art)} received",
        )

        await hunter.until(lambda s: s["ph"] == "seeking")
        await asyncio.sleep(0.3)
        together = hunter.snapshot
        check(
            "the hunter sees the chameleon once the seeking starts",
            any(other["i"] == hider.id for other in together["o"]),
            f"sees {len(together['o'])}",
        )
        check(
            "and is sent the chameleon's painting then, once",
            len(hunter.art) == 1 and hunter.art[0]["id"] == hider.id and hunter.art[0]["d"] == packed,
            f"{len(hunter.art)} received",
        )
        check("a hunter has no painting to show", hider.art == [], f"{len(hider.art)} received")

        book = ArtBook()
        book.put(hider.id, hunter.art[0]["d"] if hunter.art else "")
        seen = book.sprite(hider.id, "stand")
        mine = body_shape.sprite(canvas.surface, "stand")
        # Compared where the figure is: the cells around it are transparent,
        # and the painting sent is filled out there for the other poses.
        check(
            "what the hunter draws is the body as its owner sees it",
            seen is not None
            and pygame.image.tobytes(seen, "RGBA_PREMULT") == pygame.image.tobytes(mine, "RGBA_PREMULT"),
        )
        check(
            "which is not a body in one flat colour",
            seen is not None
            and pygame.image.tobytes(seen, "RGBA")
            != pygame.image.tobytes(body_shape.solid_sprite(BASE_COLOR, "stand"), "RGBA"),
        )

        canvas.line((10, 60), (86, 60), 6, 6, (20, 20, 20))
        repainted = pack(canvas.extended())
        await hider.send({"t": "art", "d": repainted})
        await asyncio.sleep(0.4)
        check(
            "a new stroke reaches the hunter",
            len(hunter.art) == 2 and hunter.art[-1]["d"] == repainted,
            f"{len(hunter.art)} received",
        )

        await hider.send({"t": "art", "d": "x" * 70000})
        await asyncio.sleep(0.3)
        check("an oversized painting is dropped", len(hunter.art) == 2, f"{len(hunter.art)} received")

        def hider_view(snapshot: dict) -> dict | None:
            return next((other for other in snapshot["o"] if other["i"] == hider.id), None)

        await hider.send({"t": "ps", "v": 2})
        await asyncio.sleep(0.3)
        check(
            "a pose shows only while frozen",
            hider_view(hunter.snapshot)["ps"] == 0,
            f"ps {hider_view(hunter.snapshot)['ps']} unfrozen",
        )
        await hider.send({"t": "f", "v": True})
        lying = await hunter.until(lambda s: (hider_view(s) or {}).get("ps") == 2, timeout=3)
        check("the hunter sees a frozen chameleon lying down", hider_view(lying)["fz"] is True)
        await hider.send({"t": "ps", "v": 7})
        await hider.send({"t": "f", "v": False})
        await asyncio.sleep(0.3)
        check(
            "and standing again once it moves",
            hider_view(hunter.snapshot)["ps"] == 0,
            f"ps {hider_view(hunter.snapshot)['ps']}",
        )

    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8787")))
