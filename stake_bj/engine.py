"""
Stake Blackjack Bot - 核心遊戲引擎
管理完整的遊戲循環：投注 → 決策 → 執行動作 → 統計
更新為 2024+ 最新 API 結構 (整合為 blackjackNext)
"""

import asyncio
import json
import logging
import time
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .client import StakeClient, StakeAPIError
from .graphql_queries import BLACKJACK_BET, BLACKJACK_NEXT
from .models import (
    BetResult, BlackjackState, GameAction, GameStatus, SessionStats
)
from .strategy import BasicStrategy, BettingStrategy

logger = logging.getLogger(__name__)
console = Console()


# ============================================================
# 常數
# ============================================================

# ============================================================
# 遊戲引擎
# ============================================================

class BlackjackEngine:
    """
    Stake.com BlackJack 自動投注引擎
    """

    def __init__(
        self,
        client: StakeClient,
        config: dict,
    ):
        self.client = client
        self.config = config

        # 策略設定
        self.playing_strategy = BasicStrategy(
            use_insurance=config.get("use_insurance", False)
        )
        self.betting_strategy = BettingStrategy(
            base_bet=config["bet_amount"],
            strategy=config.get("strategy", "flat"),
            martingale_multiplier=config.get("martingale_multiplier", 2.0),
            max_martingale_steps=config.get("max_martingale_steps", 5),
            min_bet=config.get("min_bet", 0.00000001),
            max_bet=config.get("max_bet", 1.0),
        )

        # 狀態
        self.stats = SessionStats()
        self._running = False
        self._current_game_id: Optional[str] = None

    # ============================================================
    # 主要遊戲循環
    # ============================================================

    async def run(self):
        """啟動自動投注主循環"""
        self._running = True
        max_rounds = self.config.get("max_rounds", 0)
        bet_delay = self.config.get("bet_delay", 1.0)
        stop_profit = self.config.get("stop_profit", 0)
        stop_loss = self.config.get("stop_loss", 0)

        # 取得初始餘額
        self.stats.start_balance = await self._get_balance()
        self.stats.current_balance = self.stats.start_balance

        console.print(Panel(
            f"[bold green]🃏 Stake Blackjack Bot 啟動[/bold green]\n"
            f"初始餘額: [cyan]{self.stats.start_balance:.8f} {self.config['currency'].upper()}[/cyan]\n"
            f"策略: [yellow]{self.config.get('strategy', 'flat')}[/yellow] | "
            f"基礎投注: [yellow]{self.config['bet_amount']:.8f}[/yellow]",
            border_style="green"
        ))

        try:
            # 啟動前先檢查是否有未完成的活躍遊戲
            await self._check_and_resume_active_game()

            while self._running:
                # 檢查停止條件
                should_stop, reason = self._check_stop_conditions(
                    stop_profit, stop_loss, max_rounds
                )
                if should_stop:
                    console.print(f"\n[yellow]🛑 停止條件達成: {reason}[/yellow]")
                    break

                # 執行一局
                await self._play_round()

                # 局間延遲
                if self._running:
                    await asyncio.sleep(bet_delay)

        except KeyboardInterrupt:
            console.print("\n[yellow]⚠️  使用者中止[/yellow]")
        except Exception as e:
            logger.error(f"引擎錯誤: {e}", exc_info=True)
            console.print(f"[red]❌ 發生錯誤: {e}[/red]")
        finally:
            self._display_final_stats()

    async def _check_and_resume_active_game(self):
        """檢查並恢復活躍遊戲"""
        from .graphql_queries import ACTIVE_BLACKJACK
        
        console.print("[dim]🔍 檢查是否有活躍中的遊戲...[/dim]")
        try:
            data = await self.client.query(ACTIVE_BLACKJACK, operation_name="ActiveBlackjack")
            active_bets = data.get("user", {}).get("activeCasinoBets", [])
            
            for bet in active_bets:
                if bet.get("game") == "blackjack":
                    game_id = bet.get("id")
                    console.print(f"[yellow]⚡ 偵測到活躍遊戲 {game_id}，正在恢復...[/yellow]")
                    
                    # 建立虛擬的 BetResult，強制設為 active=True
                    result = BetResult.from_api_response({"blackjackBet": bet}, "blackjackBet")
                    result.active = True
                    if result.state:
                        result.state.active = True
                        self._current_game_id = game_id
                        self._display_hands(result.state, initial=False)
                        final_result = await self._play_hand(game_id, result.state)
                        if final_result:
                            await asyncio.sleep(1) # 等待結算資料更新
                            await self._record_result(final_result, result.amount)
                            
        except Exception as e:
            logger.debug(f"活躍遊戲檢查失敗: {e}")

    def stop(self):
        """停止自動投注"""
        self._running = False

    # ============================================================
    # 單局遊戲流程
    # ============================================================

    async def _play_round(self):
        """執行一局完整的 Blackjack"""
        bet = self.betting_strategy.current_bet
        currency = self.config["currency"]

        console.print(f"\n[dim]{'─' * 50}[/dim]")
        console.print(
            f"[bold]局 #{self.stats.total_rounds + 1}[/bold] | "
            f"投注: [cyan]{bet:.8f} {currency.upper()}[/cyan] | "
            f"策略步數: {self.betting_strategy._martingale_step}"
        )

        # 1. 投注
        try:
            result = await self._place_bet(bet, currency)
        except Exception as e:
            console.print(f"[red]投注失敗: {e}[/red]")
            await asyncio.sleep(2)
            return

        if not result or not result.state:
            console.print("[red]投注回應異常[/red]")
            return

        self._current_game_id = result.game_id
        state = result.state

        # 顯示初始手牌
        self._display_hands(state, initial=True)

        # 2. 遊戲決策循環
        final_result = result
        if result.active:
            final_result = await self._play_hand(result.game_id, state)

        # 3. 記錄結果
        if final_result:
            await self._record_result(final_result, bet)

    async def _play_hand(self, game_id: str, state: BlackjackState) -> Optional[BetResult]:
        """執行手牌決策循環"""
        max_actions = 10  # 防止無限循環
        final_result = None

        for i in range(max_actions):
            if not state.active:
                break

            # 獲取策略決策
            action = self.playing_strategy.decide(state)
            console.print(f"  [dim]可用動作: {state.actions}[/dim]")
            logger.debug(f"策略決策: {action.value} | 可用動作: {state.actions}")
            
            # 執行動作
            try:
                result = await self._execute_action(game_id, action)
                if result is None:
                    break

                final_result = result
                state = result.state
                self._display_hands(state)

                if not state.active:
                    break
                
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"執行動作 {action.value} 失敗: {e}")
                console.print(f"[red]動作失敗: {e}[/red]")
                break

        return final_result

    # ============================================================
    # API 調用
    # ============================================================

    async def _place_bet(self, amount: float, currency: str) -> Optional[BetResult]:
        """投注"""
        data = await self.client.mutate(
            BLACKJACK_BET,
            variables={"amount": amount, "currency": currency.lower()},
            operation_name="BlackjackBet"
        )
        if "blackjackBet" in data:
            return BetResult.from_api_response(data, "blackjackBet")
        return None

    async def _execute_action(self, game_id: str, action: GameAction) -> Optional[BetResult]:
        """執行遊戲動作 (使用新的 blackjackNext)"""
        action_names = {
            GameAction.HIT: "叫牌 🎴",
            GameAction.STAND: "停叫 ✋",
            GameAction.DOUBLE: "加倍 ×2",
            GameAction.SPLIT: "分牌 ♠️",
            GameAction.INSURANCE: "購買保險 🛡️",
            GameAction.NO_INSURANCE: "不買保險 ⏩",
        }
        console.print(f"  → {action_names.get(action, action.value)}")
        
        variables = {
            "action": action.value,
            "identifier": game_id
        }

        logger.debug(f"送出 BlackjackNext: {variables}")
        data = await self.client.mutate(
            BLACKJACK_NEXT,
            variables=variables,
            operation_name="BlackjackNext"
        )
        logger.debug(f"BlackjackNext 回應: {json.dumps(data, indent=2, ensure_ascii=False)}")

        if "blackjackNext" in data:
            return BetResult.from_api_response(data, "blackjackNext")

        return None

    async def _get_balance(self) -> float:
        """取得當前餘額"""
        from .graphql_queries import USER_BALANCE

        try:
            data = await self.client.query(USER_BALANCE, operation_name="UserBalance")
            user = data.get("user", {})
            currency = self.config["currency"].lower()
            for b in user.get("balances", []):
                avail = b.get("available", {})
                if avail.get("currency", "").lower() == currency:
                    return float(avail.get("amount", 0))
        except Exception:
            pass
        return self.stats.current_balance

    # ============================================================
    # 結果記錄
    # ============================================================

    async def _record_result(self, result: BetResult, bet: float):
        """記錄本局結果並更新統計"""
        time.sleep(0.5) # 等待 API 更新
        new_balance = await self._get_balance()
        pnl = new_balance - self.stats.current_balance
        
        # 使用 BetResult 內建的判定屬性
        is_win = result.is_win
        is_push = result.is_push
        is_loss = result.is_loss
        
        # 更新統計
        self.stats.total_rounds += 1
        self.stats.total_wagered += bet
        self.stats.total_payout += (bet + pnl)

        if is_win:
            self.stats.wins += 1
            if result.payout_multiplier >= 2.5: # Blackjack
                self.stats.blackjacks += 1
                name = "Blackjack! 🎉"
                color = "green"
            else:
                name = "勝利 ✅"
                color = "green"
            self.betting_strategy.on_win()
        elif is_push:
            self.stats.pushes += 1
            name = "平局 🟡"
            color = "yellow"
            self.betting_strategy.on_push()
        else:
            self.stats.losses += 1
            name = "失敗 ❌"
            color = "red"
            self.betting_strategy.on_loss()

        self.stats.current_balance = new_balance

        console.print(
            f"\n[bold {color}]{name}[/bold {color}] | "
            f"盈虧: [{color}]{pnl:+.8f}[/{color}] | "
            f"餘額: [cyan]{self.stats.current_balance:.8f}[/cyan] (x{result.payout_multiplier})"
        )
        self._display_quick_stats()

    # ============================================================
    # 停止條件檢查
    # ============================================================

    def _check_stop_conditions(
        self, stop_profit: float, stop_loss: float, max_rounds: int
    ) -> tuple[bool, str]:
        """檢查是否需要停止"""
        net_pnl = self.stats.net_pnl

        if max_rounds > 0 and self.stats.total_rounds >= max_rounds:
            return True, f"已達最大局數 ({max_rounds})"

        if stop_profit > 0 and net_pnl >= stop_profit:
            return True, f"達到停利目標 (+{net_pnl:.8f})"

        if stop_loss > 0 and net_pnl <= -stop_loss:
            return True, f"觸發停損 ({net_pnl:.8f})"

        return False, ""

    # ============================================================
    # 顯示工具
    # ============================================================

    def _display_hands(self, state: BlackjackState, initial: bool = False):
        """顯示當前手牌"""
        prefix = "  初始發牌:" if initial else "  決策後:"
        console.print(
            f"{prefix} "
            f"[bold]玩家[/bold]: [cyan]{state.display_player_hand()}[/cyan] | "
            f"[bold]莊家[/bold]: [yellow]{state.display_dealer_hand()}[/yellow]"
        )

    def _display_quick_stats(self):
        """顯示快速統計"""
        s = self.stats
        console.print(
            f"  [dim]統計: 勝{s.wins}/敗{s.losses}/平{s.pushes} | "
            f"勝率{s.win_rate:.1f}% | 總盈虧{s.net_pnl:+.8f}[/dim]"
        )

    def _display_final_stats(self):
        """顯示最終統計報告"""
        s = self.stats

        table = Table(title="📊 遊戲統計報告", border_style="cyan", show_header=True)
        table.add_column("項目", style="bold cyan")
        table.add_column("數值", style="white", justify="right")

        table.add_row("總局數", str(s.total_rounds))
        table.add_row("勝利", f"[green]{s.wins}[/green]")
        table.add_row("失敗", f"[red]{s.losses}[/red]")
        table.add_row("平局", f"[yellow]{s.pushes}[/yellow]")
        table.add_row("Blackjack", f"🎉 {s.blackjacks}")
        table.add_row("勝率", f"{s.win_rate:.1f}%")
        table.add_row("總投注量", f"{s.total_wagered:.8f}")
        table.add_row("總回報", f"{s.total_payout:.8f}")
        table.add_row("初始餘額", f"{s.start_balance:.8f}")
        table.add_row("最終餘額", f"{s.current_balance:.8f}")

        pnl_color = "green" if s.net_pnl >= 0 else "red"
        table.add_row(
            "淨盈虧",
            f"[bold {pnl_color}]{s.net_pnl:+.8f}[/bold {pnl_color}]"
        )

        console.print("\n")
        console.print(table)
