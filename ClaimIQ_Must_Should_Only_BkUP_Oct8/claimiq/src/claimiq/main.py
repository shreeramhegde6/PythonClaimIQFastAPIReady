from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import select
from claimiq.config import get_settings
from claimiq.db import Base, SessionLocal, engine
from claimiq.models import Role, User
from claimiq.routes import limiter, router
from claimiq.security import hash_password

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        s = get_settings()
        if not db.scalar(select(User).where(User.username == s.admin_username)):
            db.add(User(username=s.admin_username, password_hash=hash_password(s.admin_password), role=Role.ADMIN)); db.commit()
    yield

app = FastAPI(title="ClaimIQ", version="1.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

@app.get("/health")
def health(): return {"status":"ok"}
