"""Shared pytest configuration: unit tests never reach the real network."""

from __future__ import annotations

import socket
from typing import Any

import pytest

_THIS_MACHINE = frozenset({"localhost", "127.0.0.1", "::1"})


@pytest.fixture(autouse=True)
def _block_real_http(request: pytest.FixtureRequest) -> None:
    """Route every ``requests`` call through ``requests_mock`` so unmocked URLs fail.

    Tests register fake responses through the ``requests_mock`` fixture. Tests marked
    ``live`` are exempt; they run only in the weekly live-check workflow.
    """
    if request.node.get_closest_marker("live") is None:
        request.getfixturevalue("requests_mock")


@pytest.fixture(autouse=True)
def _block_sockets(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any connection or host lookup that leaves this machine.

    ``requests_mock`` covers ``requests`` only. This also catches libraries that open their own
    connections, such as trafilatura's downloader, which the library must never use. Tests marked
    ``live`` are exempt.
    """
    if request.node.get_closest_marker("live") is not None:
        return
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if _on_this_machine(host):
            return real_getaddrinfo(host, *args, **kwargs)
        raise RuntimeError(f"tests must not reach the network (looked up {host!r})")

    def connect(self: socket.socket, address: Any) -> None:
        host = address[0] if isinstance(address, tuple) else address
        if not _on_this_machine(host):
            raise RuntimeError(f"tests must not reach the network (connected to {host!r})")
        real_connect(self, address)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", connect)


def _on_this_machine(host: object) -> bool:
    name = host.decode() if isinstance(host, bytes) else str(host)
    return name in _THIS_MACHINE or name.startswith("127.")
