import asyncio
import logging
from typing import Any, Optional

from curl_cffi import requests

logger = logging.getLogger(__name__)

API_URL = "https://stake.com/_api/graphql"

HEADERS_BASE = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Origin": "https://stake.com",
    "Referer": "https://stake.com/casino/games/blackjack",
    "x-language": "zh",
}


class StakeAPIError(Exception):
    """Stake API 錯誤"""
    def __init__(self, message: str, errors: Optional[list] = None):
        super().__init__(message)
        self.errors = errors or []

    def __str__(self):
        if self.errors:
            return f"{super().__str__()} | 錯誤詳情: {self.errors}"
        return super().__str__()


class StakeClient:
    """
    Stake.com GraphQL API 客戶端 (使用 curl_cffi 模擬瀏覽器)
    """

    def __init__(self, token: str, timeout: float = 30.0, user_agent: Optional[str] = None, cookie: Optional[str] = None):
        self.token = token
        self.timeout = timeout
        self.user_agent = user_agent
        self.cookie = cookie
        self.session: Optional[requests.AsyncSession] = None

    def _build_headers(self) -> dict:
        headers = HEADERS_BASE.copy()
        headers["x-access-token"] = self.token
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    async def __aenter__(self):
        self.session = requests.AsyncSession(
            impersonate="chrome124",
            timeout=self.timeout,
            headers=self._build_headers()
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
            self.session = None

    async def _request(
        self, query: str, variables: Optional[dict] = None, operation_name: Optional[str] = None
    ) -> dict[str, Any]:
        """發送 GraphQL 請求"""
        if self.session is None:
            raise RuntimeError("Session 未初始化，請使用 async with 語句")

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

        logger.debug(f"GraphQL 請求: {operation_name or 'Unknown'}, 變數: {variables}")

        for attempt in range(3):
            try:
                response = await self.session.post(API_URL, json=payload)
                
                if response.status_code == 403:
                    raise StakeAPIError("禁止存取 (403): 被 Cloudflare 阻擋。請嘗試更新 .env 中的 COOKIE。")
                
                if response.status_code >= 400:
                    logger.error(f"API 錯誤回應 (Status {response.status_code}): {response.text}")
                
                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    errors = data["errors"]
                    error_messages = [e.get("message", "未知錯誤") for e in errors]
                    raise StakeAPIError(
                        f"GraphQL 錯誤: {', '.join(error_messages)}",
                        errors=errors
                    )

                return data.get("data", {})

            except requests.errors.RequestsError as e:
                if attempt < 2:
                    logger.warning(f"請求發生錯誤，重試中... ({attempt + 1}/3): {e}")
                    await asyncio.sleep(1)
                    continue
                raise StakeAPIError(f"請求錯誤: {e}")
            except Exception as e:
                if "403" in str(e):
                    raise StakeAPIError("禁止存取 (403): Cloudflare 阻擋。")
                raise StakeAPIError(f"未知錯誤: {e}")

        raise StakeAPIError("超過最大重試次數")

    async def query(self, query: str, variables: Optional[dict] = None, operation_name: Optional[str] = None) -> dict:
        return await self._request(query, variables, operation_name)

    async def mutate(self, mutation: str, variables: Optional[dict] = None, operation_name: Optional[str] = None) -> dict:
        return await self._request(mutation, variables, operation_name)

    async def validate_token(self) -> Optional[dict]:
        from .graphql_queries import USER_BALANCE
        try:
            data = await self.query(USER_BALANCE, operation_name="UserBalance")
            return data.get("user")
        except Exception as e:
            logger.debug(f"Token 驗證詳情失敗: {e}")
            return None
