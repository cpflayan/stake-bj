"""
客戶端驗證模組
啟動前驗證所有設定是否正確
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 驗證結果
# ============================================================

@dataclass
class ValidationError:
    field: str
    message: str
    severity: str = "error"  # "error" | "warning"

    def __str__(self):
        icon = "❌" if self.severity == "error" else "⚠️"
        return f"{icon} [{self.field}] {self.message}"


@dataclass
class ValidationResult:
    errors: list[ValidationError]

    @property
    def is_valid(self) -> bool:
        return not any(e.severity == "error" for e in self.errors)

    @property
    def has_warnings(self) -> bool:
        return any(e.severity == "warning" for e in self.errors)

    def display(self):
        if not self.errors:
            return "✅ 所有驗證通過"
        return "\n".join(str(e) for e in self.errors)


# ============================================================
# 本地設定驗證 (不需要網路)
# ============================================================

SUPPORTED_CURRENCIES = {
    "usd", "btc", "eth", "ltc", "doge", "bch",
    "xrp", "trx", "eos", "bnb", "usdt"
}

SUPPORTED_STRATEGIES = {"flat", "martingale", "basic"}


def validate_config(config: dict) -> ValidationResult:
    """
    驗證設定檔案中的所有參數

    Args:
        config: 設定字典

    Returns:
        ValidationResult: 驗證結果
    """
    errors: list[ValidationError] = []

    # --- Token 驗證 ---
    token = config.get("token", "")
    if not token or token == "your_stake_access_token_here":
        errors.append(ValidationError(
            "STAKE_TOKEN",
            "Token 未設定，請在 .env 檔案中設定 STAKE_TOKEN"
        ))
    elif len(token) < 20:
        errors.append(ValidationError(
            "STAKE_TOKEN",
            "Token 長度異常，可能無效（應超過 20 個字元）",
            severity="warning"
        ))

    # --- 金額驗證 ---
    bet_amount = config.get("bet_amount", 0)
    min_bet = config.get("min_bet", 0.00000001)
    max_bet = config.get("max_bet", 1.0)

    if bet_amount < 0:
        errors.append(ValidationError(
            "BET_AMOUNT",
            "投注金額不能為負數"
        ))

    if bet_amount < min_bet:
        errors.append(ValidationError(
            "BET_AMOUNT",
            f"投注金額 ({bet_amount}) 不能小於最小投注額 ({min_bet})"
        ))

    if bet_amount > max_bet:
        errors.append(ValidationError(
            "BET_AMOUNT",
            f"投注金額 ({bet_amount}) 不能大於最大投注額 ({max_bet})"
        ))

    if min_bet < 0:
        errors.append(ValidationError(
            "MIN_BET",
            "最小投注額不能為負數"
        ))

    if max_bet <= min_bet:
        errors.append(ValidationError(
            "MAX_BET",
            f"最大投注額 ({max_bet}) 必須大於最小投注額 ({min_bet})"
        ))

    # --- 停損停利驗證 ---
    stop_profit = config.get("stop_profit", 0)
    stop_loss = config.get("stop_loss", 0)

    if stop_profit <= 0:
        errors.append(ValidationError(
            "STOP_PROFIT",
            "停利金額必須大於 0",
            severity="warning"
        ))

    if stop_loss <= 0:
        errors.append(ValidationError(
            "STOP_LOSS",
            "停損金額必須大於 0",
            severity="warning"
        ))

    if stop_profit > 0 and stop_loss > 0 and stop_profit < bet_amount:
        errors.append(ValidationError(
            "STOP_PROFIT",
            f"停利金額 ({stop_profit}) 小於基礎投注額 ({bet_amount})，可能過快停止",
            severity="warning"
        ))

    # --- 策略驗證 ---
    strategy = config.get("strategy", "flat")
    if strategy not in SUPPORTED_STRATEGIES:
        errors.append(ValidationError(
            "STRATEGY",
            f"不支援的策略: '{strategy}'。支援: {', '.join(SUPPORTED_STRATEGIES)}"
        ))

    if strategy == "martingale":
        multiplier = config.get("martingale_multiplier", 2.0)
        max_steps = config.get("max_martingale_steps", 5)

        if multiplier <= 1.0:
            errors.append(ValidationError(
                "MARTINGALE_MULTIPLIER",
                "Martingale 倍數必須大於 1.0"
            ))

        if max_steps < 1:
            errors.append(ValidationError(
                "MAX_MARTINGALE_STEPS",
                "Martingale 最大步數必須大於 0"
            ))

        # 計算最壞情況下的最大下注
        worst_case = bet_amount * (multiplier ** max_steps)
        if worst_case > max_bet:
            errors.append(ValidationError(
                "MAX_MARTINGALE_STEPS",
                f"Martingale 最壞情況下注額 ({worst_case:.8f}) 超過最大投注額 ({max_bet})，"
                f"建議減少步數或降低基礎投注額",
                severity="warning"
            ))

    # --- 貨幣驗證 ---
    currency = config.get("currency", "usd").lower()
    if currency not in SUPPORTED_CURRENCIES:
        errors.append(ValidationError(
            "CURRENCY",
            f"不支援的貨幣: '{currency}'。支援: {', '.join(sorted(SUPPORTED_CURRENCIES))}",
            severity="warning"
        ))

    # --- 延遲驗證 ---
    bet_delay = config.get("bet_delay", 1.0)
    if bet_delay < 0.5:
        errors.append(ValidationError(
            "BET_DELAY",
            f"投注延遲 ({bet_delay}s) 過短，可能觸發頻率限制，建議至少 0.5 秒",
            severity="warning"
        ))

    # --- 最大局數驗證 ---
    max_rounds = config.get("max_rounds", 0)
    if max_rounds < 0:
        errors.append(ValidationError(
            "MAX_ROUNDS",
            "最大局數不能為負數（0 = 無限）"
        ))

    return ValidationResult(errors=errors)


# ============================================================
# 線上驗證 (需要網路)
# ============================================================

async def validate_token_online(client) -> Optional[dict]:
    """
    線上驗證 Token 是否有效

    Args:
        client: StakeClient 實例

    Returns:
        使用者資訊 dict 或 None（驗證失敗）
    """
    logger.info("正在驗證 Token...")
    try:
        user = await client.validate_token()
        if user:
            logger.info(f"✅ Token 驗證成功！歡迎 {user.get('name', '未知')}")
            return user
        else:
            logger.error("❌ Token 驗證失敗：無法取得使用者資訊")
            return None
    except Exception as e:
        logger.error(f"❌ Token 驗證錯誤: {e}")
        return None


async def validate_balance(client, required_amount: float, currency: str) -> tuple[bool, float]:
    """
    驗證帳號餘額是否足夠

    Args:
        client: StakeClient 實例
        required_amount: 需要的最低金額
        currency: 貨幣類型

    Returns:
        (是否足夠, 實際餘額)
    """
    from .graphql_queries import USER_BALANCE

    try:
        data = await client.query(USER_BALANCE, operation_name="UserBalance")
        user = data.get("user", {})
        balances = user.get("balances", [])

        for balance_item in balances:
            avail = balance_item.get("available", {})
            if avail.get("currency", "").lower() == currency.lower():
                amount = float(avail.get("amount", 0))
                sufficient = amount >= required_amount
                return sufficient, amount

        return False, 0.0
    except Exception as e:
        logger.error(f"餘額查詢失敗: {e}")
        return False, 0.0


# ============================================================
# 完整啟動前驗證
# ============================================================

async def run_preflight_checks(config: dict, client) -> tuple[bool, dict]:
    """
    執行完整的啟動前驗證

    Args:
        config: 設定字典
        client: StakeClient 實例

    Returns:
        (是否通過, 結果資訊)
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    results = {}

    console.print(Panel(
        "[bold cyan]🃏 Stake Blackjack Bot - 啟動前驗證[/bold cyan]",
        border_style="cyan"
    ))

    # 1. 本地設定驗證
    console.print("\n[bold]📋 本地設定驗證...[/bold]")
    validation = validate_config(config)

    if not validation.is_valid:
        console.print("[red]❌ 設定驗證失敗！[/red]")
        for error in validation.errors:
            console.print(f"  {error}")
        return False, {"config_valid": False}

    if validation.has_warnings:
        console.print("[yellow]⚠️  設定有警告（仍可繼續）：[/yellow]")
        for error in validation.errors:
            console.print(f"  {error}")
    else:
        console.print("[green]  ✅ 本地設定驗證通過[/green]")

    results["config_valid"] = True

    # 2. Token 線上驗證
    console.print("\n[bold]🔑 Token 線上驗證...[/bold]")
    user_info = await validate_token_online(client)
    if not user_info:
        console.print("[red]  ❌ Token 驗證失敗，請檢查 STAKE_TOKEN 設定[/red]")
        return False, {**results, "token_valid": False}

    console.print(f"[green]  ✅ 已認證為: {user_info.get('name', '未知使用者')}[/green]")
    results["token_valid"] = True
    results["user"] = user_info

    # 3. 餘額驗證
    console.print("\n[bold]💰 餘額驗證...[/bold]")
    required = config["bet_amount"] * max(10, 1)  # 至少 10 局的投注金額
    sufficient, balance = await validate_balance(
        client, required, config["currency"]
    )

    console.print(f"  當前餘額: {balance:.8f} {config['currency'].upper()}")
    console.print(f"  建議最低: {required:.8f} {config['currency'].upper()}")

    if not sufficient:
        console.print(
            f"[yellow]  ⚠️  餘額不足 10 局建議金額（仍可繼續，風險較高）[/yellow]"
        )
    else:
        console.print("[green]  ✅ 餘額充足[/green]")

    results["balance"] = balance
    results["balance_sufficient"] = sufficient

    # 顯示設定摘要
    console.print("\n[bold]📊 設定摘要：[/bold]")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("項目", style="cyan")
    table.add_column("值", style="white")

    table.add_row("投注金額", f"{config['bet_amount']:.8f} {config['currency'].upper()}")
    table.add_row("策略", config["strategy"])
    table.add_row("停利", f"{config['stop_profit']:.8f}")
    table.add_row("停損", f"{config['stop_loss']:.8f}")
    table.add_row("最大局數", str(config.get("max_rounds", 0)) or "無限")
    table.add_row("投注延遲", f"{config.get('bet_delay', 1.0)}s")

    console.print(table)
    console.print()

    return True, results
