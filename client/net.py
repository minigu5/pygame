"""WebSocket client running on its own thread, bridged to pygame by queues."""

from __future__ import annotations

import asyncio
import json
import queue
import threading
from typing import Any

from web import WEB, bridge

# What the player is told when the connection ends; never a raw exception,
# whose text is in whatever language the system speaks and means little anyway.
LOST = "서버와의 연결이 끊어졌습니다."
UNREACHABLE = "서버에 연결하지 못했습니다. 서버 주소와 네트워크를 확인하세요."
REFUSED = {
    400: "방 코드가 올바르지 않습니다.",
    409: "방이 가득 찼습니다.",
}
# A browser is not told why its socket was turned away, only that it was.
WEB_REFUSED = "방에 들어가지 못했습니다. 방이 가득 찼거나 서버에 연결할 수 없습니다."


class ThreadConnection:
    def __init__(self, url: str) -> None:
        self.url = url
        self.incoming: queue.Queue[dict[str, Any]] = queue.Queue()
        self.outgoing: queue.Queue[dict[str, Any]] = queue.Queue()
        self.status = "connecting"      # then "connected", then "closed" or "failed"
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self, wait: float = 0.0) -> None:
        """Leave the room. The socket is closed from its own thread, so the
        server hears of it now rather than when the program exits; `wait`
        gives that a moment before the caller goes on to quit."""
        self._stop.set()
        if wait > 0 and self._thread.is_alive():
            self._thread.join(wait)

    @property
    def ended(self) -> bool:
        return self.status in ("closed", "failed")

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
        from websockets.exceptions import ConnectionClosed, InvalidStatus

        try:
            async with connect(self.url, open_timeout=8, close_timeout=2) as socket:
                self.status = "connected"
                reader = asyncio.create_task(self._pump_in(socket))
                try:
                    await self._pump_out(socket, reader)
                finally:
                    reader.cancel()
            if not self._stop.is_set():
                self.error = LOST
            self.status = "closed"
        except InvalidStatus as refused:
            code = refused.response.status_code
            self.error = REFUSED.get(code, f"서버가 접속을 받지 않았습니다. (HTTP {code})")
            self.status = "failed"
        except ConnectionClosed:
            self.error = LOST
            self.status = "closed"
        except Exception:
            self.error = UNREACHABLE if self.status == "connecting" else LOST
            self.status = "failed"

    async def _pump_out(self, socket: Any, reader: asyncio.Task) -> None:
        """Runs until this side leaves or the server's side of the socket ends."""
        while not self._stop.is_set() and not reader.done():
            try:
                message = self.outgoing.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.005)
                continue
            await socket.send(json.dumps(message, separators=(",", ":")))

    async def _pump_in(self, socket: Any) -> None:
        from websockets.exceptions import ConnectionClosed

        try:
            async for raw in socket:
                try:
                    self.incoming.put(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        except ConnectionClosed:
            return      # however it ended, _pump_out sees the reader is done


class WebConnection:
    """The same connection over the page's own WebSocket: see web.py."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.error: str | None = None
        self._id: int | None = None
        self._status = "connecting"

    def start(self) -> None:
        self._id = int(bridge().open(self.url))

    def close(self, wait: float = 0.0) -> None:
        if self._id is not None and not self.ended:
            self._refresh()
            bridge().close(self._id)
            if not self.ended:
                self._status = "closed"

    @property
    def status(self) -> str:
        self._refresh()
        return self._status

    @property
    def ended(self) -> bool:
        return self.status in ("closed", "failed")

    def _refresh(self) -> None:
        if self._id is None or self._status in ("closed", "failed"):
            return
        self._status = str(bridge().state(self._id))
        if self._status == "failed":
            self.error = WEB_REFUSED
        elif self._status == "closed":
            self.error = LOST

    def send(self, message: dict[str, Any]) -> None:
        if self._id is not None and self.status == "connected":
            bridge().send(self._id, json.dumps(message, separators=(",", ":")))

    def poll(self) -> list[dict[str, Any]]:
        if self._id is None:
            return []
        # One string a frame across the bridge; JSON never holds a bare newline.
        raw = str(bridge().drain(self._id) or "")
        messages = []
        for line in raw.splitlines():
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return messages


Connection = WebConnection if WEB else ThreadConnection
