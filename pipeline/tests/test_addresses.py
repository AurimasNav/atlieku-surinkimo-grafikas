from test_parsers import FIXTURES, REGISTRY

from schedule_pipeline.addresses import build_addresses, parse


def sample_points():
    return parse(
        (FIXTURES / "addresses-sample.json").read_bytes(),
        (FIXTURES / "addresses-sample.csv").read_bytes(),
    )


def test_parses_coordinates_and_house_numbers():
    points = sample_points()
    durpiu = [p for p in points if p.settlement == 10937 and p.street == 1559497]
    assert durpiu, "expected addresses on Durpių g., Avižieniai"
    assert all(54.7 < p.lat < 54.9 and 25.1 < p.lon < 25.4 for p in durpiu)
    assert all(p.number for p in durpiu)


def test_compact_table_only_has_served_places():
    table = build_addresses(sample_points(), REGISTRY, {"g10937"}, "2026-10-11T00:00:00+00:00")
    assert {place[0] for place in table["places"]} == {"g10937"}
    labels = {place[2] for place in table["places"]}
    assert "Durpių g." in labels
    lat, lon, place, number = table["points"][0]
    assert isinstance(lat, int) and isinstance(lon, int) and 0 <= place < len(table["places"])
    assert number
