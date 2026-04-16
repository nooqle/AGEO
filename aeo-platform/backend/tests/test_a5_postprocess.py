from app.workflow.a5.postprocess import _safe_ratio


def test_safe_ratio_supports_precomputed_ratio():
    assert _safe_ratio(0.25) == 0.25


def test_safe_ratio_supports_numerator_denominator():
    assert _safe_ratio(3, 12) == 0.25


def test_safe_ratio_guards_zero_denominator():
    assert _safe_ratio(3, 0) == 0.0
