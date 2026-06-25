from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

V2_ROOT: Final = Path(__file__).resolve().parents[1]
PROJECT_ROOT: Final = V2_ROOT.parent

load_dotenv(V2_ROOT / ".env")


@dataclass(frozen=True)
class ModelProfile:
    id: str
    label: str
    model: str
    base_url: str
    api_key_env: str


EDGEFN_BASE_URL: Final = "https://api.edgefn.net/v1"
DEEPSEEK_BASE_URL: Final = "https://api.deepseek.com"
DEFAULT_MODEL_ID: Final = os.getenv("DEFAULT_MODEL_ID", "minimax-m2.5")

MODEL_PROFILES: Final[dict[str, ModelProfile]] = {
    "minimax-m2.5": ModelProfile(
        id="minimax-m2.5",
        label="MiniMax-M2.5",
        model="MiniMax-M2.5",
        base_url=os.getenv("EDGEFN_BASE_URL", EDGEFN_BASE_URL),
        api_key_env="EDGEFN_API_KEY",
    ),
    "deepseek-v4-pro": ModelProfile(
        id="deepseek-v4-pro",
        label="DeepSeek-V4-Pro",
        model="deepseek-v4-pro",
        base_url=os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL),
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "glm-5.1": ModelProfile(
        id="glm-5.1",
        label="GLM-5.1",
        model="GLM-5.1",
        base_url=os.getenv("EDGEFN_BASE_URL", EDGEFN_BASE_URL),
        api_key_env="EDGEFN_API_KEY",
    ),
    "mimo-v2.5-pro": ModelProfile(
        id="mimo-v2.5-pro",
        label="MiMo-V2.5-Pro",
        model=os.getenv("MIMO_TEXT_MODEL", "mimo-v2.5-pro"),
        base_url=os.getenv("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1"),
        api_key_env="MIMO_API_KEY",
    ),
}


def get_model_profile(model_id: str | None = None) -> ModelProfile:
    selected = model_id or DEFAULT_MODEL_ID
    try:
        return MODEL_PROFILES[selected]
    except KeyError as exc:
        raise ValueError(f"Unsupported model: {selected}") from exc


@dataclass(frozen=True)
class V2Settings:
    host: str = os.getenv("V2_APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("V2_APP_PORT", "8020"))
    request_timeout_seconds: int = int(os.getenv("V2_REQUEST_TIMEOUT_SECONDS", "300"))
    svg_timeout_seconds: int = int(os.getenv("V2_SVG_TIMEOUT_SECONDS", "300"))
    svg_retry_timeout_seconds: int = int(os.getenv("V2_SVG_RETRY_TIMEOUT_SECONDS", "180"))
    json_max_tokens: int = int(os.getenv("V2_JSON_MAX_TOKENS", "6000"))
    svg_max_tokens: int = int(os.getenv("V2_SVG_MAX_TOKENS", "32000"))
    trust_environment_proxy: bool = (
        os.getenv("TRUST_ENVIRONMENT_PROXY", "false").lower() == "true"
    )

    def api_key_for(self, profile: ModelProfile) -> str:
        api_key = os.getenv(profile.api_key_env, "")
        if not api_key:
            raise RuntimeError(
                f"Missing {profile.api_key_env}. Configure it in 版本2/.env."
            )
        return api_key


settings = V2Settings()
