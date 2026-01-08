from backend.stats import StatsResponse, compute_statistics


def test_compute_statistics_returns_model():
    res = compute_statistics(["A", "B"])
    assert isinstance(res, StatsResponse)
    assert len(res.teams) == 2
    assert res.teams[0].team == "A"
