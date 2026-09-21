"""Connect two clients to a room and check roles, join events and ping/pong.

Usage: python tools/smoke_ws.py [ws://127.0.0.1:8787]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from websockets.asyncio.client import connect


async def recv(socket, timeout: float = 3.0) -> dict:
    raw = await asyncio.wait_for(socket.recv(), timeout)
    return json.loads(raw)


async def main(base: str) -> int:
    url = f"{base}/ws?room=smoke"
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
        if not ok:
            failures.append(label)

    async with connect(url) as first:
        hello_first = await recv(first)
        check("first client gets hello", hello_first.get("t") == "hello", str(hello_first))
        check("first client hunts", hello_first.get("role") == "hunter")

        async with connect(url) as second:
            hello_second = await recv(second)
            check("second client hides", hello_second.get("role") == "chameleon")

            joined = await recv(first)
            check(
                "first client sees the join",
                joined.get("t") == "j" and joined.get("id") == hello_second.get("id"),
                str(joined),
            )

            sent_at = time.monotonic()
            await second.send(json.dumps({"t": "ping", "ts": 12345}))
            pong = await recv(second)
            rtt_ms = (time.monotonic() - sent_at) * 1000
            check(
                "ping round trip",
                pong.get("t") == "pong" and pong.get("ts") == 12345,
                f"{rtt_ms:.1f} ms",
            )

        left = await recv(first)
        check("first client sees the disconnect", left.get("t") == "b", str(left))

    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8787"
    sys.exit(asyncio.run(main(base)))
