"""Application configuration loader.
Reads config.json and exposes typed pydantic models for temporal and mock server settings.
"""

import json
from pathlib import Path

from pydantic import BaseModel

CONFIG_FILE_PATH = Path(__file__).parent / "config.json"


class TemporalConfig(BaseModel):
    """Temporal server connection and task queue settings."""

    host: str
    port: int
    ui_port: int
    task_queue: str

    @property
    def server_address(self) -> str:
        """Return the full Temporal server address."""
        return f"{self.host}:{self.port}"


class MockServerConfig(BaseModel):
    """Mock callback server settings."""

    host: str
    port: int


class HttpClientConfig(BaseModel):
    """HTTP client settings for task callback activities."""

    timeout_seconds: int = 300


class AppConfig(BaseModel):
    """Top-level application configuration."""

    temporal: TemporalConfig
    mock_server: MockServerConfig
    http_client: HttpClientConfig = HttpClientConfig()


def load_config() -> AppConfig:
    """Load and validate configuration from config.json."""
    with open(CONFIG_FILE_PATH) as f:
        raw = json.load(f)
    return AppConfig.model_validate(raw)
