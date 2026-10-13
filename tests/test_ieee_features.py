import pytest

from risk_platform.ieee_features import (
    FEATURES,
    IDENTITY_FEATURES,
    MISSING,
    TRANSACTION_FEATURES,
    build_request,
    numeric,
)


def transaction():
    return dict.fromkeys(TRANSACTION_FEATURES, "1") | {"TransactionID": 42}


def test_absent_identity_and_feature_order():
    request = build_request(transaction())
    assert list(request.features) == list(FEATURES)
    assert len(request.features) == 400
    assert all(request.features[k] == MISSING for k in IDENTITY_FEATURES)
    assert all(request.features[k] == 1 for k in TRANSACTION_FEATURES)


@pytest.mark.parametrize("value", [True, "NaN", "inf", 1e100, MISSING, " ", [], "x" * 65])
def test_invalid_numeric(value):
    with pytest.raises(ValueError):
        numeric(value)


def test_blanks_only_are_missing():
    assert numeric(None) == numeric("") == MISSING
    assert numeric("0") == 0


def test_identity_join_and_label_leakage_rejected():
    ident = dict.fromkeys(IDENTITY_FEATURES, None) | {"TransactionID": 43}
    with pytest.raises(ValueError, match="mismatch"):
        build_request(transaction(), ident)
    with pytest.raises(ValueError, match="schema"):
        build_request(transaction() | {"isFraud": 1})
    tx = transaction()
    tx.pop(next(iter(TRANSACTION_FEATURES)))
    with pytest.raises(ValueError, match="schema"):
        build_request(tx)
