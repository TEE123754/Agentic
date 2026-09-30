import socket

import pytest


def test_guard_blocks_application_connections_and_dns_but_allows_internal_pair():
    for host in ("127.0.0.1", "192.0.2.1"):
        with socket.socket() as connection, pytest.raises(AssertionError, match="outbound"):
            connection.connect((host, 8765))
        with pytest.raises(AssertionError, match="outbound"):
            socket.create_connection((host, 8765))
    with pytest.raises(AssertionError, match="outbound"):
        socket.getaddrinfo("production.example.invalid", 443)
    first, second = socket.socketpair()
    with first, second:
        first.sendall(b"x")
        assert second.recv(1) == b"x"
