import ipaddress
import socket

import pytest

from site_monitor import ssrf

# Fake DNS so tests never depend on the network.
FAKE_DNS = {
    "localhost": ["127.0.0.1", "::1"],
    "example.com": ["93.184.215.14"],
    "example.org": ["96.7.128.198"],
    "internal.example": ["10.0.0.5"],
    "metadata.example": ["169.254.169.254"],
    # Public and private at once: must be rejected (the client could pick either).
    "mixed.example": ["93.184.215.14", "127.0.0.1"],
}


@pytest.fixture
def fake_dns(monkeypatch):
    def resolve(host, port):
        # Like the real resolver, an IP literal "resolves" to itself.
        try:
            return [str(ipaddress.ip_address(host))]
        except ValueError:
            pass
        try:
            return FAKE_DNS[host]
        except KeyError:
            raise socket.gaierror(f"unknown host {host}") from None

    monkeypatch.setattr(ssrf, "resolve_host", resolve)
