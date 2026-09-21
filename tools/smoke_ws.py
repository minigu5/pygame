"""Check the server end to end: handshake, roles, input, physics, disconnect.

Run `npm run dev --prefix server` first, then:
    .venv/bin/python tools/smoke_ws.py [ws://127.0.0.1:8787]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from websockets.asyncio.client import connect

LEFT, RIGHT, JUMP = 1, 2, 4

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


async def recv(socket, timeout: float = 3.0) -> dict:
    return json.loads(await asyncio.wait_for(socket.recv(), timeout))


async def recv_kind(socket, kind: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = await recv(socket, timeout)
        if message.get("t") == kind:
            return message
    raise TimeoutError(f"no {kind!r} message within {timeout}s")


async def latest_snapshot(socket) -> dict:
    """Snapshots stream at 20Hz, so drain the backlog and keep the newest."""
    newest = await recv_kind(socket, "s")
    while True:
        try:
            message = await recv(socket, 0.05)
        except (TimeoutError, asyncio.TimeoutError):
            return newest
        if message.get("t") == "s":
            newest = message


_next_frame = 1


async def hold(socket, mask: int, batches: int, batch_size: int = 4) -> dict:
    """Send `batches` input packets of a held key and return the newest snapshot."""
    global _next_frame
    for _ in range(batches):
        await socket.send(json.dumps({"t": "i", "n": _next_frame, "k": [mask] * batch_size}))
        _next_frame += batch_size
        await asyncio.sleep(batch_size / 60)
    return await latest_snapshot(socket)


async def main(base: str) -> int:
    url = f"{base}/ws?room=smoke-{int(time.time())}"

    async with connect(url) as first:
        hello_first = await recv(first)
        check("first client gets hello", hello_first.get("t") == "hello", str(hello_first))
        check("first client hunts", hello_first.get("role") == "hunter")

        async with connect(url) as second:
            hello_second = await recv(second)
            check("second client hides", hello_second.get("role") == "chameleon")

            joined = await recv_kind(first, "j")
            check("first client sees the join", joined.get("id") == hello_second.get("id"))

            await second.send(json.dumps({"t": "ping", "ts": 12345}))
            pong = await recv_kind(second, "pong")
            check("ping round trip", pong.get("ts") == 12345)

            resting = await latest_snapshot(first)
            start = resting["me"]
            check("snapshot carries my position", "x" in start and "y" in start, str(start))
            check("spawn lands on the floor", start["g"] is True, f"y={start['y']}")

            after_right = await hold(first, RIGHT, batches=8)
            check(
                "holding right moves right",
                after_right["me"]["x"] > start["x"],
                f"{start['x']} -> {after_right['me']['x']}",
            )
            check(
                "walking stays on the floor",
                after_right["me"]["y"] == start["y"],
                f"y={after_right['me']['y']}",
            )

            check(
                "snapshot acknowledges an applied input frame",
                0 < after_right["n"] < _next_frame,
                f"n={after_right['n']}",
            )

            airborne = await hold(first, JUMP, batches=3)
            check(
                "jumping leaves the floor",
                airborne["me"]["y"] < start["y"],
                f"{start['y']} -> {airborne['me']['y']}",
            )

            landed = await hold(first, 0, batches=20)
            check(
                "gravity brings me back down",
                landed["me"]["y"] == start["y"] and landed["me"]["g"] is True,
                f"y={landed['me']['y']}",
            )

            snapshot = await latest_snapshot(second)
            check(
                "each client sees the other",
                any(o["i"] == hello_first["id"] for o in snapshot["o"]),
                str(snapshot["o"]),
            )

            await second.send(json.dumps({"t": "p", "c": [10, 200, 30]}))
            await asyncio.sleep(0.2)
            painted = await latest_snapshot(first)
            check(
                "painting reaches the other client",
                any(o["c"] == [10, 200, 30] for o in painted["o"]),
                str(painted["o"]),
            )

            resting_second = await latest_snapshot(second)
            await second.send(json.dumps({"t": "f", "v": True}))
            await asyncio.sleep(0.1)
            held = await hold(second, RIGHT, batches=8)
            check(
                "freezing pins the chameleon in place",
                held["me"]["fz"] is True and held["me"]["x"] == resting_second["me"]["x"],
                f"{resting_second['me']['x']} -> {held['me']['x']}",
            )

            await second.send(json.dumps({"t": "f", "v": False}))
            await asyncio.sleep(0.1)
            released = await hold(second, RIGHT, batches=8)
            check(
                "unfreezing lets it move again",
                released["me"]["fz"] is False and released["me"]["x"] > held["me"]["x"],
                f"{held['me']['x']} -> {released['me']['x']}",
            )

            await first.send(json.dumps({"t": "f", "v": True}))
            await asyncio.sleep(0.2)
            hunter_state = await latest_snapshot(first)
            check(
                "hunters cannot freeze",
                hunter_state["me"]["fz"] is False,
            )

            wall = await hold(first, LEFT, batches=40)
            check(
                "walls stop movement",
                wall["me"]["x"] >= 32,
                f"x={wall['me']['x']}",
            )

        left = await recv_kind(first, "b")
        check("first client sees the disconnect", left.get("id") == hello_second.get("id"))

    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8787")))
