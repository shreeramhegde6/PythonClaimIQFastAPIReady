from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from claimiq.models import ClaimStatus, Role

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class LoginIn(BaseModel): username: str; password: str
class RefreshIn(BaseModel): refresh_token: str
class UserCreate(BaseModel): username: str = Field(min_length=3); password: str = Field(min_length=8); role: Role; region: str | None = None
class UserOut(ORMModel): id: str; username: str; role: Role; region: str | None; active: bool
class PolicyCreate(BaseModel): policy_number: str; policy_type: str; coverage: str; region: str
class PolicyOut(ORMModel): id: str; policy_number: str; policy_type: str; coverage: str; region: str; active: bool
class ClaimCreate(BaseModel): claim_number: str; policy_id: str; claimant: str = Field(min_length=2); claim_type: str; region: str; amount: float = Field(gt=0); assigned_to: str | None = None
class ClaimOut(ORMModel): id: str; claim_number: str; policy_id: str; claimant: str; claim_type: str; region: str; amount: float; status: ClaimStatus; assigned_to: str | None; submitted_at: datetime; closed_at: datetime | None
class StatusUpdate(BaseModel): status: ClaimStatus; note: str | None = None; justification: str | None = None
class QuestionIn(BaseModel): question: str = Field(min_length=3, max_length=2000)
