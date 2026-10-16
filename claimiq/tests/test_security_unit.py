import jwt
from claimiq.models import ClaimStatus, Role, User
from claimiq.routes import TRANSITIONS
from claimiq.security import create_access_token, hash_password, verify_password

def test_password_hash_is_not_plaintext():
    hashed=hash_password("Secret123")
    assert hashed != "Secret123"
    assert verify_password("Secret123",hashed) is True
    assert verify_password("Wrong123",hashed) is False

def test_access_token_contains_subject():
    user=User(id="user-123",username="u",password_hash="x",role=Role.ADMIN,active=True)
    token=create_access_token(user)
    payload=jwt.decode(token,"0123456789abcdef0123456789abcdef",algorithms=["HS256"])
    assert payload["sub"] == "user-123"
    assert "exp" in payload

def test_transition_map_matches_forward_workflow():
    assert TRANSITIONS[ClaimStatus.SUBMITTED] == {ClaimStatus.UNDER_REVIEW}
    assert TRANSITIONS[ClaimStatus.UNDER_REVIEW] == {ClaimStatus.APPROVED,ClaimStatus.REJECTED}
    assert TRANSITIONS[ClaimStatus.APPROVED] == {ClaimStatus.CLOSED}
    assert TRANSITIONS[ClaimStatus.REJECTED] == {ClaimStatus.CLOSED}
    assert TRANSITIONS[ClaimStatus.CLOSED] == set()
