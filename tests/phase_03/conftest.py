"""Phase-boundary checks allow numeric loopback only; model resources are already local."""

import asyncio
import json
import socket
from uuid import uuid4

import pytest

from frictionlab.configuration import CONFIG_DIRECTORY, ROOT, resolve_run
from frictionlab.planning.local_model import LocalModelRuntime


def pytest_addoption(parser):
    parser.addoption(
        "--phase3-review-saved",
        default=None,
        help="Review a specified successful run offline after a harness-only repair",
    )


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_dns = socket.getaddrinfo

    def local(host):
        return host in {"127.0.0.1", "::1", b"127.0.0.1", b"::1"}

    def connect(instance, address):
        if not isinstance(address, tuple) or not local(address[0]):
            raise AssertionError("External connection attempted during Phase 3")
        return original_connect(instance, address)

    def connect_ex(instance, address):
        if not isinstance(address, tuple) or not local(address[0]):
            raise AssertionError("External connection attempted during Phase 3")
        return original_connect_ex(instance, address)

    def dns(host, *args, **kwargs):
        if not local(host):
            raise AssertionError("External DNS attempted during Phase 3")
        return original_dns(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", dns)


@pytest.fixture
def resolved():
    return resolve_run(
        json.loads((CONFIG_DIRECTORY / "run.example.json").read_text(encoding="utf-8"))
    )


@pytest.fixture(scope="session")
def local_runtime():
    runtime = LocalModelRuntime(
        ROOT / "artifacts" / "phase3" / "acceptance" / str(uuid4()) / "model"
    )
    asyncio.run(runtime.__aenter__())
    yield runtime
    asyncio.run(runtime.close())
    assert runtime.process.poll() is not None
    assert not runtime.monitor.is_alive()
