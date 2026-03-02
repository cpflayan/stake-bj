"""
Stake Blackjack Bot - 主程式進入點
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel


# 載入環境變數

local_env = Path.cwd() / ".env.bj"
home_env = Path.home() / ".env.bj"

env_path = local_env if local_env.exists() else home_env

try:
    load_dotenv(dotenv_path=env_path, override=True)
    if env_path.exists():
        # 這裡可以用 logging 代替 print
        pass 
    else:
        print(f"ℹ️  提示：未在 {env_path} 找到 .env 檔案，將使用系統環境變數。")
except Exception as e:
    print(f"⚠️ [bold yellow]警告：讀取 .env 檔案時發生錯誤: {e}[/bold yellow]")
console = Console()


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    """設定日誌"""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    handlers: list = [logging.StreamHandler()]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def load_config() -> dict:
    """從環境變數載入設定"""
    return {
        "token": os.getenv("STAKE_TOKEN", ""),
        "bet_amount": float(os.getenv("BET_AMOUNT", "0.00000001")),
        "min_bet": float(os.getenv("MIN_BET", "0.00000001")),
        "max_bet": float(os.getenv("MAX_BET", "0.0001")),
        "stop_profit": float(os.getenv("STOP_PROFIT", "0.001")),
        "stop_loss": float(os.getenv("STOP_LOSS", "0.001")),
        "strategy": os.getenv("STRATEGY", "flat"),
        "martingale_multiplier": float(os.getenv("MARTINGALE_MULTIPLIER", "2.0")),
        "max_martingale_steps": int(os.getenv("MAX_MARTINGALE_STEPS", "5")),
        "bet_delay": float(os.getenv("BET_DELAY", "1.0")),
        "max_rounds": int(os.getenv("MAX_ROUNDS", "0")),
        "currency": os.getenv("CURRENCY", "usd").lower(),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "log_file": os.getenv("LOG_FILE", ""),
        "use_insurance": os.getenv("USE_INSURANCE", "false").lower() == "true",
        "cookie": os.getenv("COOKIE", ""),
        "user_agent": os.getenv("USER_AGENT", ""),
    }


async def main():
    """主程式"""
    from stake_bj.client import StakeClient
    from stake_bj.engine import BlackjackEngine
    from stake_bj.validator import run_preflight_checks

    config = load_config()
    setup_logging(config["log_level"], config.get("log_file") or None)

    console.print(Panel(
        "[bold cyan]♠️  Stake Blackjack Auto-Bet Bot[/bold cyan]\n"
        "[dim]基於 webdice bot 架構設計 | 基本策略 + Martingale[/dim]",
        border_style="cyan",
        width=60,
    ))

    async with StakeClient(
        token=config["token"],
        user_agent=config.get("user_agent"),
        cookie=config.get("cookie")
    ) as client:
        # 啟動前驗證
        passed, preflight_data = await run_preflight_checks(config, client)

        if not passed:
            console.print("\n[red bold]❌ 啟動前驗證未通過，程式終止[/red bold]")
            console.print("[dim]請設定 .env 檔案並填入正確的 STAKE_TOKEN[/dim]")
            sys.exit(1)

        # 確認啟動
        console.print("\n[bold yellow]⚠️  即將開始自動投注[/bold yellow]")
        console.print("[dim]按 Ctrl+C 可隨時停止[/dim]")
        console.print()

        try:
            answer = input("確認開始? (y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]已取消[/yellow]")
            return

        if answer != "y":
            console.print("[yellow]已取消[/yellow]")
            return

        # 啟動引擎
        engine = BlackjackEngine(client=client, config=config)

        try:
            await engine.run()
        except KeyboardInterrupt:
            engine.stop()
            console.print("\n[yellow]正在安全停止...[/yellow]")


def entry_point():
    """CLI 進入點"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]程式已停止[/yellow]")
    except Exception as e:
        console.print(f"\n[red]未預期的錯誤: {e}[/red]")
        logging.exception("未預期的錯誤")
        sys.exit(1)


if __name__ == "__main__":
    entry_point()
