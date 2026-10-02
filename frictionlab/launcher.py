"""One shared loopback server, with no dependency or model downloads at startup."""

import socket
import threading
from pathlib import Path

import uvicorn

from frictionlab.app import create_app


def workspace():
    return Path.home() / "FrictionLab"


class LocalServer:
    def __init__(self, root=None, port=0):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", port))
        self.socket.listen(64)
        self.port = self.socket.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.app = create_app(root or workspace(), self.port)
        self.server = uvicorn.Server(
            uvicorn.Config(
                self.app,
                host="127.0.0.1",
                port=self.port,
                access_log=False,
                log_config=None,  # Frozen GUI apps have no stdout/stderr for colored formatters.
                log_level="warning",
                timeout_graceful_shutdown=55,
            )
        )
        self.thread = None

    def run(self):
        try:
            self.server.run(sockets=[self.socket])
        finally:
            self.socket.close()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.should_exit = True

    @property
    def ready(self):
        return self.server.started
