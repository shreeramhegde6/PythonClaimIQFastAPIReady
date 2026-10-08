from claimiq.db import SessionLocal
from claimiq.models import Claim, Policy

def test_create_claim_from_active_policy(client, admin_headers, west_policy):
    response=client.post("/api/v1/claims", headers=admin_headers, json={
        "claim_number":"CLM-001","policy_id":west_policy["id"],"claimant":"Customer A",
        "claim_type":"Motor","region":"West","amount":10000,"assigned_to":None
    })
    assert response.status_code == 201
    assert response.json()["status"] == "Submitted"

def test_claim_requires_positive_amount(client, admin_headers, west_policy):
    response=client.post("/api/v1/claims", headers=admin_headers, json={
        "claim_number":"CLM-NEG","policy_id":west_policy["id"],"claimant":"Customer",
        "claim_type":"Motor","region":"West","amount":0,"assigned_to":None
    })
    assert response.status_code == 422

def test_claim_requires_valid_policy(client, admin_headers):
    response=client.post("/api/v1/claims", headers=admin_headers, json={
        "claim_number":"CLM-BADPOL","policy_id":"missing","claimant":"Customer",
        "claim_type":"Motor","region":"West","amount":100,"assigned_to":None
    })
    assert response.status_code == 422

def test_claim_rejects_inactive_policy(client, admin_headers, west_policy):
    with SessionLocal() as db:
        policy=db.get(Policy, west_policy["id"]); policy.active=False; db.commit()
    response=client.post("/api/v1/claims", headers=admin_headers, json={
        "claim_number":"CLM-INACTIVE","policy_id":west_policy["id"],"claimant":"Customer",
        "claim_type":"Motor","region":"West","amount":100,"assigned_to":None
    })
    assert response.status_code == 422

def test_claim_region_must_match_policy(client, admin_headers, west_policy):
    response=client.post("/api/v1/claims", headers=admin_headers, json={
        "claim_number":"CLM-REGION","policy_id":west_policy["id"],"claimant":"Customer",
        "claim_type":"Motor","region":"East","amount":100,"assigned_to":None
    })
    assert response.status_code == 422

def test_duplicate_claim_number_rejected(client, admin_headers, west_claim, west_policy):
    response=client.post("/api/v1/claims", headers=admin_headers, json={
        "claim_number":"CLM-WEST-001","policy_id":west_policy["id"],"claimant":"Another Customer",
        "claim_type":"Motor","region":"West","amount":500,"assigned_to":None
    })
    assert response.status_code == 409

def test_search_claims_without_filters(client, admin_headers, west_claim):
    response=client.get("/api/v1/claims", headers=admin_headers)
    assert response.status_code == 200
    assert any(x["claim_number"] == "CLM-WEST-001" for x in response.json())

def test_search_claim_by_policy_number(client, admin_headers, west_claim):
    response=client.get("/api/v1/claims", headers=admin_headers, params={"policy_number":"POL-WEST-001"})
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_search_claim_by_partial_claimant(client, admin_headers, west_claim):
    response=client.get("/api/v1/claims", headers=admin_headers, params={"claimant":"Test"})
    assert response.status_code == 200
    assert response.json()[0]["claimant"] == "Test Customer"

def test_search_claim_by_status(client, admin_headers, west_claim):
    response=client.get("/api/v1/claims", headers=admin_headers, params={"status":"Submitted"})
    assert response.status_code == 200
    assert all(x["status"] == "Submitted" for x in response.json())

def test_search_claim_no_match_returns_empty_list(client, admin_headers, west_claim):
    response=client.get("/api/v1/claims", headers=admin_headers, params={"claimant":"No Such Person"})
    assert response.status_code == 200
    assert response.json() == []

def test_adjuster_sees_same_region_claim(client, adjuster_headers, west_claim):
    response=client.get("/api/v1/claims", headers=adjuster_headers)
    assert response.status_code == 200
    assert any(x["id"] == west_claim["id"] for x in response.json())

def test_east_adjuster_cannot_see_west_claim(client, east_adjuster_headers, west_claim):
    response=client.get("/api/v1/claims", headers=east_adjuster_headers)
    assert response.status_code == 200
    assert all(x["id"] != west_claim["id"] for x in response.json())
