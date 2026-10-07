from datetime import datetime, timedelta, timezone
from claimiq.db import SessionLocal
from claimiq.models import Claim, ClaimStatus, ClaimStatusHistory

def change_status(client, headers, claim_id, status, note=None, justification=None):
    return client.patch(f"/api/v1/claims/{claim_id}/status", headers=headers, json={
        "status":status,"note":note,"justification":justification
    })

def test_forward_claim_workflow(client, adjuster_headers, west_claim):
    first=change_status(client,adjuster_headers,west_claim["id"],"Under Review","Review started")
    assert first.status_code == 200
    second=change_status(client,adjuster_headers,west_claim["id"],"Approved","Approved")
    assert second.status_code == 200
    third=change_status(client,adjuster_headers,west_claim["id"],"Closed","Closed")
    assert third.status_code == 200
    assert third.json()["closed_at"] is not None

def test_backward_transition_rejected_for_adjuster(client, adjuster_headers, west_claim):
    assert change_status(client,adjuster_headers,west_claim["id"],"Under Review").status_code == 200
    response=change_status(client,adjuster_headers,west_claim["id"],"Submitted")
    assert response.status_code == 409

def test_manager_override_with_justification(client, manager_headers, west_claim):
    response=change_status(client,manager_headers,west_claim["id"],"Closed",justification="Manager override for test")
    assert response.status_code == 200
    assert response.json()["status"] == "Closed"

def test_manager_override_without_justification_rejected(client, manager_headers, west_claim):
    response=change_status(client,manager_headers,west_claim["id"],"Closed")
    assert response.status_code == 409

def test_support_cannot_change_status(client, support_headers, west_claim):
    response=change_status(client,support_headers,west_claim["id"],"Under Review")
    assert response.status_code == 403

def test_status_history_is_created(client, adjuster_headers, west_claim):
    response=change_status(client,adjuster_headers,west_claim["id"],"Under Review","review")
    assert response.status_code == 200
    with SessionLocal() as db:
        rows=db.query(ClaimStatusHistory).filter_by(claim_id=west_claim["id"]).order_by(ClaimStatusHistory.created_at).all()
        assert len(rows) >= 2
        assert rows[-1].from_status == "Submitted"
        assert rows[-1].to_status == "Under Review"

def test_manager_analytics(client, manager_headers, west_claim):
    response=client.get("/api/v1/analytics/claims", headers=manager_headers)
    assert response.status_code == 200
    body=response.json()
    assert body["total"] == 1
    assert "approval_rate" in body
    assert "average_turnaround_days" in body
    assert "sla_breaches" in body
    assert "workload" in body

def test_admin_cannot_access_manager_only_analytics_if_contract_is_manager_only(client, admin_headers, west_claim):
    response=client.get("/api/v1/analytics/claims", headers=admin_headers)
    assert response.status_code == 403

def test_sla_breach_is_counted(client, manager_headers, west_claim):
    with SessionLocal() as db:
        claim=db.get(Claim,west_claim["id"])
        claim.submitted_at=datetime.now(timezone.utc)-timedelta(days=30)
        db.commit()
    response=client.get("/api/v1/analytics/claims", headers=manager_headers)
    assert response.status_code == 200
    assert response.json()["sla_breaches"] >= 1

def test_admin_can_view_audit_history(client, admin_headers, west_policy):
    response=client.get("/api/v1/audit", headers=admin_headers)
    assert response.status_code == 200
    actions=[row["action"] for row in response.json()]
    assert "LOGIN" in actions
    assert "CREATE" in actions

def test_manager_cannot_view_audit_history(client, manager_headers):
    response=client.get("/api/v1/audit", headers=manager_headers)
    assert response.status_code == 403
