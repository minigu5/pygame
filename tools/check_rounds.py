"""Play a room through a whole round and into the next one.

Rounds normally run three minutes, so the room takes its phase lengths from
the link the first player opens. This opens a room with very short phases and
follows it through hiding, seeking, a result and the role swap.

Run `npm run dev --prefix server` first, then:
    .venv/bin/python tools/check_rounds.py [ws://127.0.0.1:8787]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from websockets.asyncio.client import connect

RIGHT = 2

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


async def snapshot(socket, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = json.loads(await asyncio.wait_for(socket.recv(), deadline - time.monotonic()))
        if message.get("t") == "s":
            return message
    raise TimeoutError("no snapshot")


async def latest(socket, window: float = 0.3) -> dict:
    """Snapshots arrive at 20Hz, so take the newest rather than the oldest."""
    newest = await snapshot(socket)
    deadline = time.monotonic() + window
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return newest
        try:
            message = json.loads(await asyncio.wait_for(socket.recv(), remaining))
        except (TimeoutError, asyncio.TimeoutError):
            return newest
        if message.get("t") == "s":
            newest = message


async def wait_for_phase(socket, phase: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = await snapshot(socket, deadline - time.monotonic())
        if message["ph"] == phase:
            return message
    raise TimeoutError(f"room never reached {phase!r}")


async def main(base: str) -> int:
    room = f"rounds-{int(time.time())}"
    url = f"{base}/ws?room={room}&hide=5&seek=6&result=2"

    async with connect(url) as first:
        await first.recv()
        alone = await snapshot(first)
        check("one player alone waits", alone["ph"] == "waiting", str(alone["ph"]))

        async with connect(f"{base}/ws?room={room}") as second:
            await second.recv()

            hiding = await wait_for_phase(first, "hiding")
            check("a second player starts the round", hiding["rd"] == 1, f"round {hiding['rd']}")

            roles = {
                (await latest(first))["me"]["rl"],
                (await latest(second))["me"]["rl"],
            }
            check("one hunts and one hides", roles == {"hunter", "chameleon"}, str(roles))

            hunter, hider = (first, second) if hiding["me"]["rl"] == "hunter" else (second, first)

            # The hunter is shut out while the others hide.
            start = (await latest(hunter))["me"]["x"]
            for sequence in range(1, 9):
                await hunter.send(json.dumps({"t": "i", "n": sequence * 4, "k": [RIGHT] * 4}))
                await asyncio.sleep(0.07)
            held = await latest(hunter)
            check("the hunter cannot move while they hide", held["me"]["x"] == start, f"x={held['me']['x']}")

            moved_start = (await latest(hider))["me"]["x"]
            for sequence in range(1, 9):
                await hider.send(json.dumps({"t": "i", "n": sequence * 4, "k": [RIGHT] * 4}))
                await asyncio.sleep(0.07)
            moved = await latest(hider)
            check("the hider can move", moved["me"]["x"] > moved_start, f"{moved_start} -> {moved['me']['x']}")

            seeking = await wait_for_phase(hunter, "seeking")
            check("hiding gives way to seeking", seeking["ph"] == "seeking")

            free_start = (await latest(hunter))["me"]["x"]
            for sequence in range(20, 28):
                await hunter.send(json.dumps({"t": "i", "n": sequence * 4, "k": [RIGHT] * 4}))
                await asyncio.sleep(0.07)
            released = await latest(hunter)
            check("the hunter moves once seeking starts", released["me"]["x"] > free_start)

            result = await wait_for_phase(hunter, "result")
            check(
                "running out of time hands it to the hiders",
                result.get("win") == "chameleons",
                str(result.get("win")),
            )

            second_round = await wait_for_phase(hunter, "hiding")
            check("a new round follows", second_round["rd"] == 2, f"round {second_round['rd']}")
            check(
                "the roles swap",
                (await latest(hunter))["me"]["rl"] == "chameleon",
                "previous hunter now hides",
            )

        stranded = await wait_for_phase(first, "waiting", timeout=10)
        check("the room waits again once alone", stranded["ph"] == "waiting")

    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8787")))
