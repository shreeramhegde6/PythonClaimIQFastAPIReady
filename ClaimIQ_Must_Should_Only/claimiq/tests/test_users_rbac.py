from conftest import login, bearer

def test_admin_can_create_user(client, admin_headers):
    response = client.post("/api/v1/users", headers=admin_headers, json={
        "username":"new_adjuster","password":"Password123","role":"Claims Adjuster","region":"West"
    })
    assert response.status_code == 201
    assert response.json()["username"] == "new_adjuster"
    assert response.json()["role"] == "Claims Adjuster"

def test_duplicate_username_rejected(client, admin_headers):
    payload={"username":"duplicate","password":"Password123","role":"Support Agent","region":"West"}
    assert client.post("/api/v1/users", headers=admin_headers, json=payload).status_code == 201
    response=client.post("/api/v1/users", headers=admin_headers, json=payload)
    assert response.status_code == 409

def test_short_password_validation(client, admin_headers):
    response=client.post("/api/v1/users", headers=admin_headers, json={
        "username":"shortpw","password":"123","role":"Support Agent","region":"West"
    })
    assert response.status_code == 422

def test_manager_cannot_list_users(client, manager_headers):
    response=client.get("/api/v1/users", headers=manager_headers)
    assert response.status_code == 403

def test_support_cannot_create_user(client, support_headers):
    response=client.post("/api/v1/users", headers=support_headers, json={
        "username":"blocked","password":"Password123","role":"Support Agent","region":"West"
    })
    assert response.status_code == 403

def test_admin_can_deactivate_user(client, admin_headers, seeded_users):
    user_id=seeded_users["support"]["id"]
    response=client.patch(f"/api/v1/users/{user_id}/active", headers=admin_headers, params={"active":False})
    assert response.status_code == 200
    assert response.json()["active"] is False
    login_response=client.post("/api/v1/auth/login", json={"username":"support","password":"ChangeMe123!"})
    assert login_response.status_code == 401

def test_deactivate_missing_user_returns_404(client, admin_headers):
    response=client.patch("/api/v1/users/not-found/active", headers=admin_headers, params={"active":False})
    assert response.status_code == 404
