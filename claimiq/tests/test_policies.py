def test_admin_creates_policy(client, admin_headers):
    response=client.post("/api/v1/policies", headers=admin_headers, json={
        "policy_number":"POL-001","policy_type":"Motor","coverage":"Coverage","region":"West"
    })
    assert response.status_code == 201
    body=response.json()
    assert body["policy_number"] == "POL-001"
    assert body["active"] is True

def test_duplicate_policy_number_rejected(client, admin_headers, west_policy):
    response=client.post("/api/v1/policies", headers=admin_headers, json={
        "policy_number":"POL-WEST-001","policy_type":"Motor","coverage":"Another coverage","region":"West"
    })
    assert response.status_code == 409

def test_get_policy_by_id(client, admin_headers, west_policy):
    response=client.get(f"/api/v1/policies/{west_policy['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["id"] == west_policy["id"]

def test_get_missing_policy_returns_404(client, admin_headers):
    response=client.get("/api/v1/policies/missing-policy-id", headers=admin_headers)
    assert response.status_code == 404

def test_adjuster_cannot_view_other_region_policy(client, admin_headers, east_adjuster_headers):
    response=client.post("/api/v1/policies", headers=admin_headers, json={
        "policy_number":"POL-WEST-009","policy_type":"Motor","coverage":"Coverage","region":"West"
    })
    assert response.status_code == 201
    policy_id=response.json()["id"]
    response=client.get(f"/api/v1/policies/{policy_id}", headers=east_adjuster_headers)
    assert response.status_code == 403

def test_support_can_view_same_region_policy(client, support_headers, west_policy):
    response=client.get(f"/api/v1/policies/{west_policy['id']}", headers=support_headers)
    assert response.status_code == 200

def test_manager_cannot_create_policy_if_admin_only_contract(client, manager_headers):
    response=client.post("/api/v1/policies", headers=manager_headers, json={
        "policy_number":"POL-MGR-001","policy_type":"Motor","coverage":"Coverage","region":"West"
    })
    assert response.status_code == 403
