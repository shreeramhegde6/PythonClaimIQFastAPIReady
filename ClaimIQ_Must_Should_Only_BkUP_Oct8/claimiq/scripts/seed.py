from sqlalchemy import select
from claimiq.db import Base, SessionLocal, engine
from claimiq.models import Policy, Role, User
from claimiq.security import hash_password
Base.metadata.create_all(engine)
with SessionLocal() as db:
    for name, role, region in [("manager",Role.MANAGER,None),("adjuster",Role.ADJUSTER,"West"),("support",Role.SUPPORT,"West")]:
        if not db.scalar(select(User).where(User.username == name)): db.add(User(username=name,password_hash=hash_password("ChangeMe123!"),role=role,region=region))
    if not db.scalar(select(Policy)):
        db.add(Policy(policy_number="POL-MOTOR-001",policy_type="Motor",coverage="Accidental damage subject to approved policy wording.",region="West"))
    db.commit()
print("Seed complete")
