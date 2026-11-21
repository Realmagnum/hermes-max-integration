"""A shared finite size-scaled timeout used by gateway and standalone."""
from max.mixins import upload_stream


def test_size_budget_has_floor_ceiling_and_scales():
    budget = getattr(upload_stream, "upload_timeout", None)
    assert callable(budget), "shared size-based upload timeout is missing"
    assert budget(1) == 120
    assert budget(250_000_000) > budget(50_000_000)
    assert budget(4_000_000_000) == 3600
