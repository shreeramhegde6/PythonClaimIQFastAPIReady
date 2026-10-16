from claimiq.models import ClaimStatus
from claimiq.routes import TRANSITIONS

def test_valid_forward_transitions():
    assert ClaimStatus.UNDER_REVIEW in TRANSITIONS[ClaimStatus.SUBMITTED]
    assert ClaimStatus.APPROVED in TRANSITIONS[ClaimStatus.UNDER_REVIEW]
    assert ClaimStatus.REJECTED in TRANSITIONS[ClaimStatus.UNDER_REVIEW]
    assert ClaimStatus.CLOSED in TRANSITIONS[ClaimStatus.APPROVED]

def test_no_backward_transition():
    assert ClaimStatus.SUBMITTED not in TRANSITIONS[ClaimStatus.APPROVED]
