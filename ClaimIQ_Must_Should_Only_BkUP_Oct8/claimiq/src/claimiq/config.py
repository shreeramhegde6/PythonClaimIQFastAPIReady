from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://claimiq:claimiq@localhost:5432/claimiq"
    jwt_secret: str = "change-me"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    admin_username: str = "admin"
    admin_password: str = "ChangeMe123!"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"
    sla_days: int = 7
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = ""
    azure_openai_embedding_deployment: str = ""
    azure_search_endpoint: str = ""
    azure_search_key: str = ""
    azure_search_index: str = "claimiq-chunks"
    rag_top_k: int = 5
    rag_min_score: float = 0.01
    rag_max_context_chars: int = 14000
    document_dir: str = "uploads"

@lru_cache
def get_settings() -> Settings:
    return Settings()
