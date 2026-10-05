"""What the client needs from the browser when it runs there (built with pygbag).

In a browser there are no threads and no sockets of Python's own: the page's
WebSocket and fetch do the talking. Their callbacks stay on the JavaScript
side, which only fills buffers; Python reads them once a frame, so nothing
ever calls back into it.
"""

from __future__ import annotations

import sys

WEB = sys.platform == "emscripten"

_BRIDGE = """
window.chameleon = window.chameleon || {
    sockets: {}, fetches: {}, next: 1,
    open(url) {
        const id = this.next++;
        const entry = { socket: new WebSocket(url), inbox: [], state: "connecting" };
        entry.socket.onopen = () => { entry.state = "connected"; };
        entry.socket.onmessage = (event) => { entry.inbox.push(event.data); };
        entry.socket.onclose = () => { entry.state = entry.state === "connecting" ? "failed" : "closed"; };
        this.sockets[id] = entry;
        return id;
    },
    state(id) { return this.sockets[id] ? this.sockets[id].state : "closed"; },
    send(id, text) {
        const entry = this.sockets[id];
        if (entry && entry.socket.readyState === 1) entry.socket.send(text);
    },
    drain(id) {
        const entry = this.sockets[id];
        if (!entry || !entry.inbox.length) return "";
        return entry.inbox.splice(0).join("\\n");
    },
    close(id) {
        const entry = this.sockets[id];
        if (entry) { entry.socket.close(); delete this.sockets[id]; }
    },
    fetch(url) {
        const id = this.next++;
        const entry = { done: false, status: 0, text: "" };
        this.fetches[id] = entry;
        fetch(url, { cache: "no-store" })
            .then((response) => { entry.status = response.status; return response.text(); })
            .then((text) => { entry.text = text; entry.done = true; })
            .catch(() => { entry.status = 0; entry.done = true; });
        return id;
    },
    fetched(id) { return this.fetches[id].done; },
    fetchStatus(id) { return this.fetches[id].status; },
    fetchText(id) { const text = this.fetches[id].text; delete this.fetches[id]; return text; },
};
"""

_bridge = None


def bridge():
    """The page's side of the conversation, installed on first use."""
    global _bridge
    if _bridge is None:
        import platform

        platform.window.eval(_BRIDGE)
        _bridge = platform.window.chameleon
    return _bridge


def page_server() -> str:
    """The game server is whatever served this page."""
    import platform

    location = platform.window.location
    scheme = "wss" if str(location.protocol) == "https:" else "ws"
    return f"{scheme}://{location.host}"
