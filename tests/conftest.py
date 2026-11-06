import pytest
import requests


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not contact the network")

    monkeypatch.setattr(requests.Session, "request", blocked)
