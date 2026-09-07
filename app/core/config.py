"""
FaceFlow AI — Configuration
All settings are read from environment variables (or .env file).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: str = "development"

    # SerpApi
    serpapi_api_key: str = ""

    # Alchemy / Ethereum
    alchemy_api_key: str = ""
    sepolia_rpc_url: str = "https://eth-sepolia.g.alchemy.com/v2/demo"
    chain_id: int = 11155111

    # Blockchain wallet
    blockchain_private_key: str = ""

    # Smart contract
    contract_address: str = ""

    # Face matching
    face_match_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    face_strong_match_threshold: float = Field(default=0.75, ge=0.0, le=1.0)

    # Limits
    max_upload_mb: int = Field(default=10, ge=1)
    search_max_candidates: int = Field(default=10, ge=1, le=50)
    request_timeout_seconds: int = Field(default=15, ge=5)

    # InsightFace
    insightface_model_name: str = "buffalo_l"

    # Gemini AI
    gemini_api_key: str = ""

    # TMDB
    tmdb_api_key: str = ""

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def serpapi_configured(self) -> bool:
        return bool(self.serpapi_api_key and self.serpapi_api_key != "your_serpapi_key_here")

    @property
    def blockchain_configured(self) -> bool:
        return bool(
            self.blockchain_private_key
            and self.contract_address
            and self.blockchain_private_key != "0xyour_private_key_here"
            and self.contract_address != "0xyour_contract_address_here"
        )

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and "your" not in self.gemini_api_key)

    @property
    def tmdb_configured(self) -> bool:
        return bool(self.tmdb_api_key and self.tmdb_api_key != "your_tmdb_api_key_here")


# Singleton settings instance
settings = Settings()
