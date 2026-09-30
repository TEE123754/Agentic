"""In-process fixture tests; no website, browser, or model is contacted."""

import json
import shutil
import socket
import threading

import pytest
from fastapi.testclient import TestClient

from frictionlab.api import create_app
from frictionlab.configuration import CONFIG_DIRECTORY


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    original_connect = socket.socket.connect
    original_pair = socket.socketpair
    trusted_pair = threading.local()

    def rejected(*args, **kwargs):
        raise AssertionError("Phase 1 validation attempted an outbound connection")

    def guarded_connect(instance, address):
        # Windows creates its event-loop self-pipe with a private loopback socket pair.
        # Only the standard-library socketpair call may open that internal connection.
        if getattr(trusted_pair, "active", False) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(instance, address)
        return rejected()

    def internal_socketpair(*args, **kwargs):
        trusted_pair.active = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            trusted_pair.active = False

    monkeypatch.setattr(socket, "socketpair", internal_socketpair)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", rejected)
    monkeypatch.setattr(socket, "create_connection", rejected)
    monkeypatch.setattr(socket, "getaddrinfo", rejected)


@pytest.fixture
def payload():
    return json.loads((CONFIG_DIRECTORY / "run.example.json").read_text(encoding="utf-8"))


@pytest.fixture
def registry(tmp_path):
    destination = tmp_path / "configs"
    shutil.copytree(CONFIG_DIRECTORY, destination)
    return destination


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(artifact_root=tmp_path / "reports")) as instance:
        yield instance
