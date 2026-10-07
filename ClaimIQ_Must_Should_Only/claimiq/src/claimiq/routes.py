import hashlib
from datetime import datetime, timezone
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from claimiq.config import get_settings
from claimiq.db import get_db
from claimiq.models import AuditLog, ChatQueryLog, Claim, ClaimNote, ClaimStatus, ClaimStatusHistory, Document, Policy, RefreshToken, Role, User
from claimiq.rag import RAGService, save_document
from claimiq.schemas import ClaimCreate, ClaimOut, LoginIn, PolicyCreate, PolicyOut, QuestionIn, RefreshIn, StatusUpdate, UserCreate, UserOut
from claimiq.security import create_access_token, create_refresh_token, current_user, hash_password, require_roles, verify_password

router = APIRouter(prefix="/api/v1")
limiter = Limiter(key_func=get_remote_address)

def audit(db, actor, action, entity_type, entity_id=None, detail=None):
    db.add(AuditLog(actor_id=getattr(actor, "id", None), action=action, entity_type=entity_type, entity_id=entity_id, detail=detail or {}))

@router.post("/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username))
    if not user or not user.active or not verify_password(data.password, user.password_hash):
        audit(db, None, "LOGIN_FAILED", "User"); db.commit(); raise HTTPException(401, "Invalid credentials")
    audit(db, user, "LOGIN", "User", user.id); db.commit()
    return {"access_token": create_access_token(user), "refresh_token": create_refresh_token(db, user), "token_type": "bearer"}

@router.post("/auth/refresh")
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(data.refresh_token.encode()).hexdigest()
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.revoked == False))
    if not token or token.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc): raise HTTPException(401, "Invalid refresh token")
    token.revoked = True; user = db.get(User, token.user_id); db.commit()
    return {"access_token": create_access_token(user), "refresh_token": create_refresh_token(db, user), "token_type": "bearer"}

@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))): return db.scalars(select(User).order_by(User.username)).all()

@router.post("/users", response_model=UserOut, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    item = User(username=data.username, password_hash=hash_password(data.password), role=data.role, region=data.region); db.add(item)
    try: db.flush(); audit(db, user, "CREATE", "User", item.id); db.commit(); db.refresh(item); return item
    except IntegrityError: db.rollback(); raise HTTPException(409, "Username already exists")

@router.patch("/users/{username}/active")
def set_user_active(username: str, active: bool, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    item = db.get(User, username)
    if not item: raise HTTPException(404, "User not found")
    item.active = active; audit(db, user, "ACTIVATE" if active else "DEACTIVATE", "User", item.username); db.commit(); return {"id": item.id, "active": item.active}

@router.post("/policies", response_model=PolicyOut, status_code=201)
def create_policy(data: PolicyCreate, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    item = Policy(**data.model_dump()); db.add(item)
    try: db.flush(); audit(db, user, "CREATE", "Policy", item.id); db.commit(); db.refresh(item); return item
    except IntegrityError: db.rollback(); raise HTTPException(409, "Policy number already exists")

@router.get("/policies/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: str, db: Session = Depends(get_db), user=Depends(current_user)):
    item = db.get(Policy, policy_id)
    if not item: raise HTTPException(404, "Policy not found")
    if user.role in {Role.ADJUSTER, Role.SUPPORT} and user.region and item.region != user.region: raise HTTPException(403, "Policy is outside your region")
    return item

@router.post("/claims", response_model=ClaimOut, status_code=201)
def create_claim(data: ClaimCreate, db: Session = Depends(get_db), user=Depends(current_user)):
    policy = db.get(Policy, data.policy_id)
    if not policy or not policy.active: raise HTTPException(422, "Policy must be valid and active")
    if data.region != policy.region: raise HTTPException(422, "Claim region must match policy region")
    if user.role in {Role.ADJUSTER, Role.SUPPORT} and user.region != data.region: raise HTTPException(403, "Cannot create claim outside your region")
    item = Claim(**data.model_dump()); db.add(item)
    try:
        db.flush(); db.add(ClaimStatusHistory(claim_id=item.id, from_status=None, to_status=item.status.value, actor_id=user.id)); audit(db, user, "CREATE", "Claim", item.id); db.commit(); db.refresh(item); return item
    except IntegrityError: db.rollback(); raise HTTPException(409, "Claim number already exists")

def scoped_claims(query, user):
    if user.role == Role.ADJUSTER: return query.where(or_(Claim.assigned_to == user.id, Claim.region == user.region))
    if user.role == Role.SUPPORT and user.region: return query.where(Claim.region == user.region)
    return query

@router.get("/claims", response_model=list[ClaimOut])
def search_claims(policy_number: str | None = None, claimant: str | None = None, status: ClaimStatus | None = None, db: Session = Depends(get_db), user=Depends(current_user)):
    query = scoped_claims(select(Claim), user)
    if policy_number: query = query.join(Policy, Claim.policy_id == Policy.id).where(Policy.policy_number.ilike(f"%{policy_number}%"))
    if claimant: query = query.where(Claim.claimant.ilike(f"%{claimant}%"))
    if status: query = query.where(Claim.status == status)
    return db.scalars(query.order_by(Claim.submitted_at.desc())).all()

TRANSITIONS = {ClaimStatus.SUBMITTED:{ClaimStatus.UNDER_REVIEW}, ClaimStatus.UNDER_REVIEW:{ClaimStatus.APPROVED,ClaimStatus.REJECTED}, ClaimStatus.APPROVED:{ClaimStatus.CLOSED}, ClaimStatus.REJECTED:{ClaimStatus.CLOSED}, ClaimStatus.CLOSED:set()}

@router.patch("/claims/{claim_id}/status", response_model=ClaimOut)
def update_status(claim_id: str, data: StatusUpdate, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADJUSTER, Role.MANAGER))):
    item = db.get(Claim, claim_id)
    if not item: raise HTTPException(404, "Claim not found")
    if user.role == Role.ADJUSTER and not (item.assigned_to == user.id or item.region == user.region): raise HTTPException(403, "Claim is outside your assignment or region")
    override = user.role == Role.MANAGER and bool(data.justification and data.justification.strip())
    if data.status not in TRANSITIONS[item.status] and not override: raise HTTPException(409, "Invalid status transition")
    old = item.status; item.status = data.status
    if data.status == ClaimStatus.CLOSED: item.closed_at = datetime.now(timezone.utc)
    db.add(ClaimStatusHistory(claim_id=item.id, from_status=old.value, to_status=data.status.value, actor_id=user.id, justification=data.justification))
    if data.note: db.add(ClaimNote(claim_id=item.id, author_id=user.id, note=data.note))
    audit(db, user, "STATUS_CHANGE", "Claim", item.id, {"from":old.value,"to":data.status.value,"override":override}); db.commit(); db.refresh(item); return item

@router.post("/documents", status_code=201)
def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    name = file.filename or "document"; data = file.file.read()
    if len(data) > 20_000_000: raise HTTPException(413, "File exceeds 20 MB")
    if not name.lower().endswith((".pdf", ".docx", ".txt")): raise HTTPException(415, "Only PDF, DOCX and TXT are supported")
    digest = hashlib.sha256(data).hexdigest()
    if db.scalar(select(Document).where(Document.content_hash == digest)): raise HTTPException(409, "Document already exists")
    item = Document(name=name, file_path="", content_hash=digest, uploaded_by=user.id); db.add(item); db.flush()
    try:
        item.file_path = save_document(data, name); item.chunk_count = RAGService().ingest(data, item.id, name); audit(db, user, "UPLOAD", "Document", item.id); db.commit()
        return {"id":item.id,"name":name,"chunks":item.chunk_count,"active":True}
    except Exception as exc:
        db.rollback()
        print("EXCEPTION TYPE:", type(exc).__name__)
        print("EXCEPTION MESSAGE:", str(exc))
        print("EXCEPTION REPR:", repr(exc))
        raise HTTPException(
            status_code=503,
            detail=f"Document processing failed: {type(exc).__name__}: {str(exc)}"
        )from exc
    #except Exception as exc: db.rollback(); raise HTTPException(503, f"Document processing failed: {type(exc).__name__}") from exc

@router.get("/documents")
def list_documents(db: Session = Depends(get_db), user=Depends(current_user)): return db.scalars(select(Document).order_by(Document.created_at.desc())).all()

@router.patch("/documents/{document_id}/active")
def set_document_active(document_id: str, active: bool, db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))):
    item = db.get(Document, document_id)
    if not item: raise HTTPException(404, "Document not found")
    try: RAGService().set_active(document_id, active)
    except Exception as exc: raise HTTPException(503, f"Search update failed: {type(exc).__name__}") from exc
    item.active = active; audit(db, user, "ACTIVATE" if active else "DEACTIVATE", "Document", item.id); db.commit(); return {"id":item.id,"active":item.active}

@router.post("/ai/query")
@limiter.limit("10/minute")
def ask_ai(request: Request, data: QuestionIn, db: Session = Depends(get_db), user=Depends(current_user)):
    try: result = RAGService().ask(data.question)
    #except Exception as exc: raise HTTPException(503, f"AI service unavailable: {type(exc).__name__}") from exc
    except Exception as exc:
        print("AI ERROR TYPE:", type(exc).__name__)
        print("AI ERROR:", str(exc))
        print("AI ERROR REPR:", repr(exc))
        raise HTTPException(
            status_code=503,
            detail=f"AI service unavailable: {type(exc).__name__}: {str(exc)}"
        ) from exc

    db.add(ChatQueryLog(user_id=user.id, question=data.question, sources=result["sources"], low_confidence=result["low_confidence"], prompt_tokens=result["prompt_tokens"], completion_tokens=result["completion_tokens"])); audit(db, user, "AI_QUERY", "ChatQueryLog", detail={"source_count":len(result["sources"]),"low_confidence":result["low_confidence"]}); db.commit(); return result

@router.get("/analytics/claims")
def claims_analytics(db: Session = Depends(get_db), user=Depends(require_roles(Role.MANAGER))):
    rows = db.scalars(select(Claim)).all()
    if not rows: return {"total":0,"approval_rate":0,"rejection_rate":0,"average_turnaround_days":0,"sla_breaches":0,"workload":{}}
    frame = pd.DataFrame([{"status":x.status.value,"assigned_to":x.assigned_to or "Unassigned","submitted_at":x.submitted_at,"closed_at":x.closed_at} for x in rows]).drop_duplicates()
    completed = frame[frame.closed_at.notna()].copy()
    average = 0 if completed.empty else (pd.to_datetime(completed.closed_at, utc=True)-pd.to_datetime(completed.submitted_at, utc=True)).dt.total_seconds().div(86400).mean()
    age = (pd.Timestamp.now(tz="UTC")-pd.to_datetime(frame.submitted_at, utc=True)).dt.total_seconds().div(86400)
    breached = ((age > get_settings().sla_days) & ~frame.status.isin(["Closed"])).sum()
    return {"total":len(frame),"approval_rate":round((frame.status=="Approved").mean()*100,2),"rejection_rate":round((frame.status=="Rejected").mean()*100,2),"average_turnaround_days":round(float(average),2),"sla_breaches":int(breached),"workload":frame.assigned_to.value_counts().to_dict()}

@router.get("/audit")
def audit_history(limit: int = Query(100, le=500), db: Session = Depends(get_db), user=Depends(require_roles(Role.ADMIN))): return db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
