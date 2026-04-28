from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    PROJECT_NAME: str
    VERSION: str
    API_V1_STR: str
    
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 2

    LLM_MODEL: str = "gpt-oss:120b-cloud"
    LLM_TIMEOUT: int = 120
    OLLAMA_API_KEY: str
    LLM_BASE_URL: str
    AUTH_SECRET_KEY: str
    ACCESS_TOKEN_TTL_SECONDS: int

    #database 
    MILVUS_URI: str
    MILVUS_TOKEN: str
    MILVUS_DB_NAME: str
    NEO4J_URI: str
    NEO4J_USERNAME: str
    NEO4J_PASSWORD: str

    # EMBDDING
    EMBEDDING_NAME: str

    # redis
    REDIS_URI: str
    # Đọc từ file .env

    # postgres
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DATABASE: str
    POSTGRES_WORKSPACE: str = "legal_ai_platform"
    POSTGRES_ENABLE_VECTOR: bool = False
    DATABASE_URL: str
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
