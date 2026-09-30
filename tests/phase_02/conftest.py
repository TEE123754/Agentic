"""Phase 2 acceptance uses owned loopback services; all Python outbound sockets fail."""

import json
import socket

import pytest

from frictionlab.configuration import CONFIG_DIRECTORY, resolve_run


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_dns = socket.getaddrinfo

    def local(host):
        return host in {"127.0.0.1", "::1", b"127.0.0.1", b"::1"}

    def connect(instance, address):
        if not isinstance(address, tuple) or not local(address[0]):
            raise AssertionError("External connection attempted during Phase 2")
        return original_connect(instance, address)

    def connect_ex(instance, address):
        if not isinstance(address, tuple) or not local(address[0]):
            raise AssertionError("External connection attempted during Phase 2")
        return original_connect_ex(instance, address)

    def dns(host, *args, **kwargs):
        if not local(host):
            raise AssertionError("External DNS attempted during Phase 2")
        return original_dns(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", dns)


@pytest.fixture
def resolved():
    payload = json.loads((CONFIG_DIRECTORY / "run.example.json").read_text(encoding="utf-8"))
    return resolve_run(payload)
