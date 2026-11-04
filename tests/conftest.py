"""Every test runs like this: no internet, no search key, and its own admin log and search store.
So a test can never use the key, never write to the real outputs/, and CI can't go red because a server is down."""

import socket

import pytest

from halflife import config
from halflife.molecules import who_atc
from halflife.sources import fda_novel


@pytest.fixture(autouse=True)
def sealed(monkeypatch, tmp_path):
    tried = []

    def blocked(self_or_host, *args, **kwargs):
        tried.append(str(args[0] if args else self_or_host))
        raise OSError("no internet in tests")

    real_connect = socket.socket.connect

    def connect(self, address):
        if self.family == socket.AF_UNIX:
            return real_connect(self, address)
        return blocked(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    monkeypatch.setattr(config, "ADMIN_LOG", tmp_path / "admin_log.csv")
    monkeypatch.setattr(config, "WEB_SEARCH_STORE", tmp_path / "web_search.json")
    monkeypatch.setattr(config, "WHO_ATC_STORE", tmp_path / "who_atc.json")
    monkeypatch.setattr(who_atc, "DELAY", 0)
    fda_novel._year_rows.cache_clear()
    yield
    assert not tried, f"this test tried to reach the internet: {tried[:3]}"
