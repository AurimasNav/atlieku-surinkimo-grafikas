from datetime import date
from urllib.error import HTTPError

from schedule_pipeline import build, snapshot


def test_snapshots_load():
    registry, taken = snapshot.load_registry()
    points, taken_points = snapshot.load_points()
    assert len(registry.settlements) > 1000
    assert len(points) > 50_000
    assert taken == taken_points
    durpiu = [p for p in points if p.settlement == 10937 and p.street == 1559497]
    assert durpiu and 54.7 < durpiu[0].lat < 54.9


def test_falls_back_to_snapshot_when_blocked():
    def blocked():
        raise HTTPError("https://get.data.gov.lt", 500, "Internal Server Error", {}, None)

    data, note = build._live_or_snapshot(
        "Address Register", blocked, lambda: ("snapshot", "2026-10-11")
    )
    assert data == "snapshot"
    assert "live source unavailable" in note and "2026-10-11" in note


def test_old_snapshot_asks_for_refresh(monkeypatch):
    def blocked():
        raise TimeoutError("timed out")

    class Later(date):
        @classmethod
        def today(cls):
            return date(2027, 1, 1)

    monkeypatch.setattr(build, "date", Later)
    _, note = build._live_or_snapshot("Address points", blocked, lambda: ([], "2026-10-11"))
    assert "please refresh" in note
