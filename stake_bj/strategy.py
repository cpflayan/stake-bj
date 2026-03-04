"""
BlackJack 基本策略引擎
基於數學最優決策表（基本策略表）
更新為支援 2024+ 牌面格式
"""

import logging
from typing import Optional

from .models import BlackjackState, GameAction, hand_value, is_pair, is_soft_hand

logger = logging.getLogger(__name__)

# ============================================================
# 基本策略查詢表
# ============================================================

# --- 硬牌策略表 (Hard Totals) ---
HARD_STRATEGY: dict[tuple[int, int], str] = {}

# 5-8點: 永遠叫牌
for total in range(5, 9):
    for dealer in range(2, 12):
        HARD_STRATEGY[(total, dealer)] = "H"

# 9點
for dealer in range(2, 12):
    if dealer in range(3, 7):
        HARD_STRATEGY[(9, dealer)] = "D"
    else:
        HARD_STRATEGY[(9, dealer)] = "H"

# 10點
for dealer in range(2, 12):
    if dealer in range(2, 10):
        HARD_STRATEGY[(10, dealer)] = "D"
    else:
        HARD_STRATEGY[(10, dealer)] = "H"

# 11點
for dealer in range(2, 12):
    if dealer != 11:
        HARD_STRATEGY[(11, dealer)] = "D"
    else:
        HARD_STRATEGY[(11, dealer)] = "H"

# 12點
for dealer in range(2, 12):
    if dealer in range(4, 7):
        HARD_STRATEGY[(12, dealer)] = "S"
    else:
        HARD_STRATEGY[(12, dealer)] = "H"

# 13-16點
for total in range(13, 17):
    for dealer in range(2, 12):
        if dealer in range(2, 7):
            HARD_STRATEGY[(total, dealer)] = "S"
        else:
            HARD_STRATEGY[(total, dealer)] = "H"

# 17-21點: 永遠停叫
for total in range(17, 22):
    for dealer in range(2, 12):
        HARD_STRATEGY[(total, dealer)] = "S"

# --- 軟牌策略表 (Soft Totals, A+X) ---
SOFT_STRATEGY: dict[tuple[int, int], str] = {}

# Soft 13, 14
for other in [2, 3]:
    for dealer in range(2, 12):
        if dealer in [5, 6]:
            SOFT_STRATEGY[(other, dealer)] = "D"
        else:
            SOFT_STRATEGY[(other, dealer)] = "H"

# Soft 15, 16
for other in [4, 5]:
    for dealer in range(2, 12):
        if dealer in range(4, 7):
            SOFT_STRATEGY[(other, dealer)] = "D"
        else:
            SOFT_STRATEGY[(other, dealer)] = "H"

# Soft 17
for dealer in range(2, 12):
    if dealer in range(3, 7):
        SOFT_STRATEGY[(6, dealer)] = "D"
    else:
        SOFT_STRATEGY[(6, dealer)] = "H"

# Soft 18
for dealer in range(2, 12):
    if dealer in [3, 4, 5, 6]:
        SOFT_STRATEGY[(7, dealer)] = "D"
    elif dealer in [2, 7, 8]:
        SOFT_STRATEGY[(7, dealer)] = "S"
    else:
        SOFT_STRATEGY[(7, dealer)] = "H"

# Soft 19+
for other in range(8, 12):
    for dealer in range(2, 12):
        SOFT_STRATEGY[(other, dealer)] = "S"

# --- 分牌策略表 (Pairs) ---
PAIR_STRATEGY: dict[tuple[int, int], str] = {}

# A-A
for dealer in range(2, 12):
    PAIR_STRATEGY[(11, dealer)] = "P"

# 2-2, 3-3
for pair_val in [2, 3]:
    for dealer in range(2, 12):
        if dealer in range(2, 8):
            PAIR_STRATEGY[(pair_val, dealer)] = "P"
        else:
            PAIR_STRATEGY[(pair_val, dealer)] = "H"

# 4-4
for dealer in range(2, 12):
    if dealer in [5, 6]:
        PAIR_STRATEGY[(4, dealer)] = "P"
    else:
        PAIR_STRATEGY[(4, dealer)] = "H"

# 5-5
for dealer in range(2, 12):
    if dealer in range(2, 10):
        PAIR_STRATEGY[(5, dealer)] = "D"
    else:
        PAIR_STRATEGY[(5, dealer)] = "H"

# 6-6
for dealer in range(2, 12):
    if dealer in range(2, 7):
        PAIR_STRATEGY[(6, dealer)] = "P"
    else:
        PAIR_STRATEGY[(6, dealer)] = "H"

# 7-7
for dealer in range(2, 12):
    if dealer in range(2, 8):
        PAIR_STRATEGY[(7, dealer)] = "P"
    else:
        PAIR_STRATEGY[(7, dealer)] = "H"

# 8-8
for dealer in range(2, 12):
    PAIR_STRATEGY[(8, dealer)] = "P"

# 9-9
for dealer in range(2, 12):
    if dealer in [7, 10, 11]:
        PAIR_STRATEGY[(9, dealer)] = "S"
    else:
        PAIR_STRATEGY[(9, dealer)] = "P"

# T-T
for dealer in range(2, 12):
    PAIR_STRATEGY[(10, dealer)] = "S"


# ============================================================
# 策略引擎
# ============================================================

class BasicStrategy:
    """
    BlackJack 基本策略引擎
    """

    def __init__(self, use_insurance: bool = False):
        self.use_insurance = use_insurance

    def decide(self, state: BlackjackState) -> GameAction:
        player_cards = state.player_cards
        dealer_upcard_str = state.dealer_upcard

        if not player_cards or not dealer_upcard_str:
            return GameAction.STAND

        # 1. 處理保險 (Insurance / Even Money)
        # 用戶規則：只要莊家 A，不論玩家狀態一律跳過保險 (noInsurance)
        # 
        # 判斷保險階段的可靠方法：
        # - 莊家只有 1 張牌可見（初始發牌後）
        # - 且 actions 歷史中尚未出現 noInsurance 或 insurance（保險尚未決定）
        # Stake 的 actions 是「歷史紀錄」：noInsurance 在其中 = 保險已處理完
        is_dealer_ace = state.dealer_upcard_value == 11
        dealer_card_count = len(state.dealer_cards)
        has_done_insurance = "noInsurance" in state.actions or "insurance" in state.actions
        is_insurance_phase = is_dealer_ace and dealer_card_count == 1 and not has_done_insurance

        if is_insurance_phase:
            logger.debug("保險階段 (莊家 A 1 張牌，尚未決定)，執行不買保險 (actions: %s)", state.actions)
            return GameAction.NO_INSURANCE

        player_total = state.player_total
        dealer_val = state.dealer_upcard_value

        # 2. 分牌策略 (只有在非保險處理時進入)
        if state.can_split and is_pair(player_cards):
            card = player_cards[0]
            rank = "10" if card.startswith("10") else card[0].upper()
            from .models import CARD_VALUES
            pair_val = CARD_VALUES.get(rank, 0)
            
            action_code = PAIR_STRATEGY.get((pair_val, dealer_val), "H")
            if action_code == "P":
                return GameAction.SPLIT
            # 分牌後的其他處理（加倍、停叫等）由後續邏輯判斷

        # 3. 軟牌策略
        if state.is_soft and len(player_cards) == 2:
            non_ace_val = player_total - 11
            action_code = SOFT_STRATEGY.get((non_ace_val, dealer_val))
            if action_code:
                return self._apply_action(action_code, state, "軟牌")

        # 4. 硬牌策略
        if player_total >= 21:
            return GameAction.STAND

        clamped_total = min(max(player_total, 5), 21)
        action_code = HARD_STRATEGY.get((clamped_total, dealer_val), "H")
        return self._apply_action(action_code, state, "硬牌")

    def _apply_action(
        self, action_code: str, state: BlackjackState, hand_type: str
    ) -> GameAction:
        action_map = {
            "H": GameAction.HIT,
            "S": GameAction.STAND,
            "D": GameAction.DOUBLE,
            "P": GameAction.SPLIT,
        }

        action = action_map.get(action_code, GameAction.HIT)

        # 處理加倍限制：只有2張牌時才能加倍，否則改為叫牌
        if action == GameAction.DOUBLE and not state.can_double:
            logger.debug(f"{hand_type} 策略加倍，但已超過2張牌，改為叫牌")
            return GameAction.HIT

        # 處理分牌限制：只有對子才能分牌
        if action == GameAction.SPLIT and not state.can_split:
            logger.debug(f"{hand_type} 策略分牌，但非對子，改為停叫/叫牌")
            return GameAction.HIT if state.player_total < 17 else GameAction.STAND

        return action


# ============================================================
# 投注策略
# ============================================================

class BettingStrategy:
    """投注金額策略 (不變)"""

    def __init__(
        self,
        base_bet: float,
        strategy: str = "flat",
        martingale_multiplier: float = 2.0,
        max_martingale_steps: int = 5,
        min_bet: float = 0.00000001,
        max_bet: float = 1.0,
    ):
        self.base_bet = base_bet
        self.strategy = strategy
        self.martingale_multiplier = martingale_multiplier
        self.max_martingale_steps = max_martingale_steps
        self.min_bet = min_bet
        self.max_bet = max_bet
        self._current_bet = base_bet
        self._loss_streak = 0
        self._martingale_step = 0

    @property
    def current_bet(self) -> float:
        return round(max(self.min_bet, min(self._current_bet, self.max_bet)), 8)

    def on_win(self):
        if self.strategy == "martingale":
            self._loss_streak = 0
            self._martingale_step = 0
            self._current_bet = self.base_bet

    def on_loss(self):
        if self.strategy == "martingale":
            self._loss_streak += 1
            self._martingale_step = min(self._martingale_step + 1, self.max_martingale_steps)
            self._current_bet = self.base_bet * (self.martingale_multiplier ** self._martingale_step)

    def on_push(self):
        pass

    def reset(self):
        self._current_bet = self.base_bet
        self._loss_streak = 0
        self._martingale_step = 0
