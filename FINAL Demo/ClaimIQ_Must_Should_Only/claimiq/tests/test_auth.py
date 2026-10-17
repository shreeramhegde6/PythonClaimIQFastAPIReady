import hashlib
from datetime import datetime, timezone
from sqlalchemy import select
from claimiq.db import SessionLocal
from claimiq.models import RefreshToken
from conftest import bearer, login

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status":"ok"}

def test_admin_login_success(client):
    body = login(client)
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

def test_login_bad_password(client):
    response = client.post("/api/v1/auth/login", json={"username":"admin","password":"wrong-password"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

def test_login_unknown_user(client):
    response = client.post("/api/v1/auth/login", json={"username":"missing","password":"ChangeMe123!"})
    assert response.status_code == 401

def test_protected_endpoint_without_token(client):
    response = client.get("/api/v1/users")
    assert response.status_code in (401, 403)

def test_refresh_token_rotates(client):
    tokens = login(client)
    response = client.post("/api/v1/auth/refresh", json={"refresh_token":tokens["refresh_token"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"] != tokens["refresh_token"]

def test_refresh_token_cannot_be_reused(client):
    tokens = login(client)
    first = client.post("/api/v1/auth/refresh", json={"refresh_token":tokens["refresh_token"]})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/refresh", json={"refresh_token":tokens["refresh_token"]})
    assert second.status_code == 401

def test_invalid_bearer_token(client):
    response = client.get("/api/v1/users", headers=bearer("not-a-jwt"))
    assert response.status_code == 401
