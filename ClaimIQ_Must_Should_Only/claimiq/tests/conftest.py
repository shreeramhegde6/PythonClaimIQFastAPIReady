import os
from pathlib import Path
import pytest

# Force a disposable SQLite database before ClaimIQ modules are imported.
os.environ["DATABASE_URL"] = "sqlite:///./test_claimiq.db"
os.environ["JWT_SECRET"] = "0123456789abcdef0123456789abcdef"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "ChangeMe123!"
os.environ["DOCUMENT_DIR"] = "test_uploads"

from fastapi.testclient import TestClient
from sqlalchemy import select
from claimiq.db import Base, SessionLocal, engine
from claimiq.main import app
from claimiq.models import Policy, Role, User
from claimiq.security import hash_password

@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(User(username="admin", password_hash=hash_password("ChangeMe123!"), role=Role.ADMIN))
        db.commit()
    yield
    Base.metadata.drop_all(engine)

@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def login(client, username="admin", password="ChangeMe123!"):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def admin_headers(client):
    return bearer(login(client)["access_token"])

@pytest.fixture
def seeded_users(client, admin_headers):
    users = [
        {"username":"manager","password":"ChangeMe123!","role":"Claims Manager","region":None},
        {"username":"adjuster","password":"ChangeMe123!","role":"Claims Adjuster","region":"West"},
        {"username":"support","password":"ChangeMe123!","role":"Support Agent","region":"West"},
        {"username":"east_adjuster","password":"ChangeMe123!","role":"Claims Adjuster","region":"East"},
    ]
    created = {}
    for payload in users:
        response = client.post("/api/v1/users", headers=admin_headers, json=payload)
        assert response.status_code == 201, response.text
        created[payload["username"]] = response.json()
    return created

@pytest.fixture
def manager_headers(client, seeded_users):
    return bearer(login(client, "manager")["access_token"])

@pytest.fixture
def adjuster_headers(client, seeded_users):
    return bearer(login(client, "adjuster")["access_token"])

@pytest.fixture
def support_headers(client, seeded_users):
    return bearer(login(client, "support")["access_token"])

@pytest.fixture
def east_adjuster_headers(client, seeded_users):
    return bearer(login(client, "east_adjuster")["access_token"])

@pytest.fixture
def west_policy(client, admin_headers):
    response = client.post("/api/v1/policies", headers=admin_headers, json={
        "policy_number":"POL-WEST-001","policy_type":"Motor","coverage":"Motor test coverage","region":"West"
    })
    assert response.status_code == 201, response.text
    return response.json()

@pytest.fixture
def west_claim(client, admin_headers, west_policy, seeded_users):
    response = client.post("/api/v1/claims", headers=admin_headers, json={
        "claim_number":"CLM-WEST-001","policy_id":west_policy["id"],"claimant":"Test Customer",
        "claim_type":"Motor","region":"West","amount":25000,"assigned_to":seeded_users["adjuster"]["id"]
    })
    assert response.status_code == 201, response.text
    return response.json()
