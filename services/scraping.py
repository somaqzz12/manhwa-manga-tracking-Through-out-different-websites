from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests


def is_valid_http_url(raw_url: str) -> bool:
    try:
        parsed = urlparse((raw_url or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def is_public_http_url(raw_url: str) -> bool:
    if not is_valid_http_url(raw_url):
        return False
    try:
        host = (urlparse((raw_url or "").strip()).hostname or "").strip()
        if not host:
            return False
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        if not infos:
            return False
        for info in infos:
            ip_txt = info[4][0]
            ip = ipaddress.ip_address(ip_txt)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return False
        return True
    except Exception:
        return False


def fetch_public_url(
    session: requests.Session,
    url: str,
    *,
    timeout_seconds: int,
    max_redirects: int = 5,
    **kwargs,
) -> requests.Response:
    current = (url or "").strip()
    timeout = kwargs.pop("timeout", timeout_seconds)
    for _ in range(max_redirects + 1):
        if not is_public_http_url(current):
            raise ValueError("Blocked URL (private/internal host)")
        res = session.get(current, timeout=timeout, allow_redirects=False, **kwargs)
        if not res.is_redirect:
            return res
        location = (res.headers.get("Location") or "").strip()
        if not location:
            return res
        current = urljoin(current, location)
    raise ValueError("Too many redirects")

