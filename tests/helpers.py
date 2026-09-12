"""Stubs shared by several test modules: an event-recording log and a
stand-in for a requests.Response."""


class StubLog:
    """Records every event() call as (kind, fields)."""

    def __init__(self):
        self.events = []

    def event(self, kind, **fields):
        self.events.append((kind, fields))

    def kinds(self):
        return [kind for kind, _ in self.events]


class FakeResponse:
    """A requests.Response with a canned payload, status and body text."""

    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
