from __future__ import annotations

import logging
import time

import httpx
from openai import OpenAI

from .config import ModelProfile, get_model_profile, settings

logger = logging.getLogger(__name__)


class V2LLMClient:
    def __init__(self, model_id: str | None = None) -> None:
        self.profile: ModelProfile = get_model_profile(model_id)
        self.text_model = self.profile.model
        self.client = OpenAI(
            api_key=settings.api_key_for(self.profile),
            base_url=self.profile.base_url,
            timeout=settings.request_timeout_seconds,
            max_retries=0,
            http_client=httpx.Client(
                trust_env=settings.trust_environment_proxy,
                timeout=settings.request_timeout_seconds,
            ),
        )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.4,
        max_tokens: int = 8000,
        task_name: str = "版本2文本任务",
        timeout_seconds: int | None = None,
        retry_timeout_seconds: int | None = None,
        max_attempts: int = 2,
    ) -> str:
        timeout_seconds = timeout_seconds or settings.request_timeout_seconds
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            attempt_timeout = (
                retry_timeout_seconds
                if attempt > 0 and retry_timeout_seconds is not None
                else timeout_seconds
            )
            started = time.perf_counter()
            try:
                response = self.client.chat.completions.create(
                    model=self.text_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=attempt_timeout,
                )
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("模型返回了空内容")
                logger.info(
                    "版本2模型任务完成 | 任务=%s | 模型=%s | 耗时=%.2f秒",
                    task_name,
                    self.text_model,
                    time.perf_counter() - started,
                )
                return content.strip()
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "版本2模型任务失败 | 任务=%s | 尝试=%s/%s | 错误=%s",
                    task_name,
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                if attempt < max_attempts - 1:
                    time.sleep(2**attempt)
        raise RuntimeError(
            f"版本2模型请求失败：任务={task_name}，尝试次数={max_attempts}，最后错误={last_error}"
        )
