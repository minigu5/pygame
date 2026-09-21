"""WebSocket client running on its own thread, bridged to pygame by queues."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any


class Connection:
    def __init__(self, url: str) -> None:
        self.url = url
        self.incoming: queue.Queue[dict[str, Any]] = queue.Queue()
        self.outgoing: queue.Queue[dict[str, Any]] = queue.Queue()
        self.status = "connecting"
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()

    def send(self, message: dict[str, Any]) -> None:
        self.outgoing.put(message)

    def poll(self) -> list[dict[str, Any]]:
        messages = []
        while True:
            try:
                messages.append(self.incoming.get_nowait())
            except queue.Empty:
                return messages

    def _run(self) -> None:
        asyncio.run(self._main())

    async def _main(self) -> None:
        from websockets.asyncio.client import connect

        try:
            async with connect(self.url) as socket:
                self.status = "connected"
                await asyncio.gather(
                    self._pump_out(socket),
                    self._pump_in(socket),
                )
        except Exception as exc:
            self.status = "failed"
            self.error = f"{type(exc).__name__}: {exc}"

    async def _pump_out(self, socket: Any) -> None:
        while not self._stop.is_set():
            try:
                message = self.outgoing.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.005)
                continue
            await socket.send(json.dumps(message, separators=(",", ":")))

    async def _pump_in(self, socket: Any) -> None:
        async for raw in socket:
            if self._stop.is_set():
                return
            try:
                self.incoming.put(json.loads(raw))
            except json.JSONDecodeError:
                continue
