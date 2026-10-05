"""Check the waiting room and the lobby's room list.

A room is listed while someone is in it, its host (whoever has been there
longest) sets it up and starts the round, and leaving in the middle of a round
never strands the people who stay.

Run `npm run dev --prefix server` first, then:
    .venv/bin/python tools/check_lobby.py [ws://127.0.0.1:8787]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

from lobby import fetch_rooms  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


async def recv_kind(socket, kind: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = json.loads(await asyncio.wait_for(socket.recv(), deadline - time.monotonic()))
        if message.get("t") == kind:
            return message
    raise TimeoutError(f"no {kind!r} message within {timeout}s")


async def room_info(socket, wanted, timeout: float = 5.0) -> dict:
    """The first room message that satisfies `wanted`."""
    deadline = time.monotonic() + timeout
    while True:
        info = await recv_kind(socket, "r", deadline - time.monotonic())
        if wanted(info):
            return info


async def wait_for_phase(socket, phase: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = await recv_kind(socket, "s", deadline - time.monotonic())
        if message["ph"] == phase:
            return message
    raise TimeoutError(f"room never reached {phase!r}")


async def listed(base: str, code: str) -> dict | None:
    rooms = await asyncio.to_thread(fetch_rooms, base)
    return next((room for room in rooms if room["code"] == code), None)


async def main(base: str) -> int:
    code = f"lobby-{int(time.time())}"
    url = f"{base}/ws?room={code}"

    check("a room nobody is in is not listed", await listed(base, code) is None)

    async with connect(f"{url}&name={quote('숨바꼭질 한 판')}&hide=5&seek=10&result=2") as host:
        hello = await recv_kind(host, "hello")
        opened = await recv_kind(host, "r")
        check(
            "whoever opens the room is its host",
            opened["host"] == hello["id"] and opened["n"] == 1,
            str(opened),
        )
        check("the room takes its name from the link", opened["name"] == "숨바꼭질 한 판", opened["name"])

        await asyncio.sleep(0.3)
        entry = await listed(base, code)
        check(
            "the lobby lists it with its name, headcount and phase",
            entry is not None
            and entry["name"] == "숨바꼭질 한 판"
            and entry["players"] == 1
            and entry["capacity"] == opened["max"]
            and entry["phase"] == "waiting",
            str(entry),
        )
        check(
            "a listing says nothing about who is where",
            entry is not None and set(entry) == {"code", "name", "players", "capacity", "phase"},
            str(entry and sorted(entry)),
        )

        await host.send(json.dumps({"t": "start"}))
        await asyncio.sleep(0.4)
        check(
            "the host cannot start alone",
            (await recv_kind(host, "s"))["ph"] == "waiting",
        )

        await host.send(json.dumps({"t": "cfg", "name": "  새   이름\n", "max": 2, "hide": 7, "seek": 9999}))
        changed = await room_info(host, lambda info: info["max"] == 2)
        check(
            "the host changes the name, the headcount and the phase lengths",
            changed["name"] == "새 이름" and changed["hide"] == 7,
            str(changed),
        )
        check("settings stay within their limits", changed["seek"] == 600, f"seek {changed['seek']}")

        async with connect(url) as guest:
            guest_hello = await recv_kind(guest, "hello")
            seen = await recv_kind(guest, "r")
            check(
                "a guest is told the room's settings on joining",
                seen["name"] == "새 이름" and seen["n"] == 2 and seen["host"] == hello["id"],
                str(seen),
            )

            try:
                async with connect(url):
                    check("a full room turns the next player away", False, "third player got in")
            except InvalidStatus as refused:
                check(
                    "a full room turns the next player away",
                    refused.response.status_code == 409,
                    f"HTTP {refused.response.status_code}",
                )

            await room_info(host, lambda info: info["n"] == 2)
            await guest.send(json.dumps({"t": "cfg", "name": "손님이 바꾼 이름"}))
            await host.send(json.dumps({"t": "cfg", "max": 1}))
            kept = await room_info(host, lambda info: True)
            check(
                "a guest cannot change settings, and the room cannot shrink below its players",
                kept["name"] == "새 이름" and kept["max"] == 2,
                str(kept),
            )

            await host.send(json.dumps({"t": "cfg", "max": 3, "seek": 10}))
            await room_info(host, lambda info: info["max"] == 3)
            await host.send(json.dumps({"t": "start"}))
            hiding = await wait_for_phase(guest, "hiding")
            check("the host's start begins the round for everyone", hiding["rd"] == 1)
            await asyncio.sleep(0.3)
            entry = await listed(base, code)
            check(
                "the lobby shows the round under way",
                entry is not None and entry["phase"] == "hiding" and entry["players"] == 2,
                str(entry),
            )

            await host.send(json.dumps({"t": "cfg", "name": "판 도중"}))
            await asyncio.sleep(0.3)
            entry = await listed(base, code)
            check("settings are fixed once the round starts", entry is not None and entry["name"] == "새 이름")

            async with connect(url) as late:
                await recv_kind(late, "hello")
                watching = await recv_kind(late, "s")
                check(
                    "someone who joins mid-round watches until the next one",
                    watching["me"]["rl"] == "spectator" and watching["ph"] == "hiding",
                    str(watching["me"]["rl"]),
                )

                # The host opened the room, so the host hunts first. Leaving
                # now must not leave the other two hiding from nobody.
                await host.close()
                handed = await room_info(guest, lambda info: info["host"] != hello["id"])
                check(
                    "when the host leaves, the next longest here takes over",
                    handed["host"] == guest_hello["id"] and handed["n"] == 2,
                    str(handed),
                )
                result = await wait_for_phase(guest, "result", timeout=5)
                check(
                    "a round whose hunter left goes to the hiders",
                    result.get("win") == "chameleons",
                    str(result.get("win")),
                )
                again = await wait_for_phase(guest, "hiding", timeout=8)
                check("and the next round follows with those who stayed", again["rd"] == 2, f"round {again['rd']}")

            back = await wait_for_phase(guest, "waiting", timeout=5)
            check(
                "left alone mid-round, the last player is back in the waiting room",
                back["me"]["rl"] == "spectator",
                str(back["me"]["rl"]),
            )
            await asyncio.sleep(0.3)
            entry = await listed(base, code)
            check(
                "and the lobby shows the room waiting again",
                entry is not None and entry["phase"] == "waiting" and entry["players"] == 1,
                str(entry),
            )

    await asyncio.sleep(0.5)
    check("a room everyone has left drops off the list", await listed(base, code) is None)

    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8787")))
