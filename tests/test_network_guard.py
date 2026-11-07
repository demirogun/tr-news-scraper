"""Unit tests can't reach the network, whatever library tries: only this machine is allowed."""

from __future__ import annotations

import socket

import pytest


def test_connecting_to_another_host_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="tests must not reach the network"):
        socket.create_connection(("192.0.2.1", 443), timeout=1)


def test_looking_up_a_host_name_fails_loudly() -> None:
    with pytest.raises(RuntimeError, match="tests must not reach the network"):
        socket.getaddrinfo("www.example.com.tr", 443)


def test_this_machine_stays_reachable_for_tools_that_need_it() -> None:
    assert socket.getaddrinfo("localhost", 0)
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        with socket.create_connection(server.getsockname(), timeout=1):
            pass
