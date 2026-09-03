"""Every outbound request this project makes.

A caller hands us a URL and we fetch it. `POST /catalog/import/` takes
one from an unauthenticated body. A page we read can point at another
host. So the address is never ours to trust.

The guard resolves the host and refuses anything not public: loopback,
private ranges, link-local, and the rest. Cloud metadata sits on
169.254.169.254, and a database on localhost.

It runs in `Session.send`. A redirect lands there too, so a page cannot
bounce the fetch somewhere the caller could not name.

One gap is worth knowing. The name is resolved twice, here and by the
connection. A record that changes between them is not caught. Closing
that means pinning the address into the socket.
"""

import ipaddress
import socket
from urllib.parse import urlparse

import requests

ALLOWED_SCHEMES = frozenset({"http", "https"})


class BlockedAddress(requests.exceptions.InvalidURL):
    """The address is not one a status page can be served from."""


def _refuses(ip):
    """Anything that is not a public address on the internet."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def check(url):
    """Raise unless this address is one we are willing to fetch."""
    parts = urlparse(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise BlockedAddress(f"{parts.scheme or 'that'} is not a scheme we fetch.")
    host = parts.hostname
    if not host:
        raise BlockedAddress("No host to fetch.")
    try:
        found = socket.getaddrinfo(host, parts.port or 0, proto=socket.IPPROTO_TCP)
    except OSError as error:
        # Fail closed. A name we cannot resolve is a name we do not fetch.
        raise BlockedAddress(f"{host} does not resolve.") from error
    for info in found:
        address = ipaddress.ip_address(info[4][0])
        if _refuses(address):
            raise BlockedAddress(f"{host} resolves to {address}, which is not public.")
    return url


class GuardedSession(requests.Session):
    """A session that checks where it is going, on every hop."""

    def send(self, request, **kwargs):
        check(request.url)
        return super().send(request, **kwargs)


# One session for the whole process, so connections are pooled and every
# fetch goes through the guard. An adapter given its own session in a
# test uses that instead.
session = GuardedSession()
