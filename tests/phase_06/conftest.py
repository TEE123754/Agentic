"""Phase 6 browser checks may contact only their owned loopback fixtures."""

import socket

import pytest


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_dns = socket.getaddrinfo

    def allowed(address):
        return isinstance(address, tuple) and address[0] in {
            "127.0.0.1",
            "::1",
            b"127.0.0.1",
            b"::1",
        }

    def connect(instance, address):
        if not allowed(address):
            raise AssertionError("External connection attempted during Phase 6")
        return original_connect(instance, address)

    def connect_ex(instance, address):
        if not allowed(address):
            raise AssertionError("External connection attempted during Phase 6")
        return original_connect_ex(instance, address)

    def dns(host, *args, **kwargs):
        if host not in {"127.0.0.1", "::1", b"127.0.0.1", b"::1"}:
            raise AssertionError("External DNS attempted during Phase 6")
        return original_dns(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", dns)
