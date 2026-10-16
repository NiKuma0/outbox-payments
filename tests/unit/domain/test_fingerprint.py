import pytest

from outbox_payments.domain import Money, request_fingerprint
from tests.cases._helpers import as_params
from tests.cases.domain.fingerprint import (
    BASE_REQUEST,
    FINGERPRINT_CASES,
    FingerprintCase,
    FingerprintRequest,
)


def fingerprint_of(request: FingerprintRequest) -> str:
    return request_fingerprint(
        money=Money(request["amount"], request["currency"]),
        description=request["description"],
        metadata=request["metadata"],
        webhook_url=request["webhook_url"],
    )


@pytest.mark.parametrize("case", as_params(FINGERPRINT_CASES))
def test_request_fingerprint(case: FingerprintCase) -> None:
    variant: FingerprintRequest = {**BASE_REQUEST, **case["overrides"]}

    same = fingerprint_of(variant) == fingerprint_of(BASE_REQUEST)

    assert same is case["same_fingerprint"]


def test_fingerprint_is_a_sha256_hex_digest() -> None:
    digest = fingerprint_of(BASE_REQUEST)

    assert len(digest) == 64
    assert int(digest, 16) >= 0
