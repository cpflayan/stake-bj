"""
BlackJack 遊戲模型
定義牌面值、手牌狀態和遊戲狀態資料結構
更新為 2024+ 最新 API 結構 (rank/suit 物件格式)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


# ============================================================
# 枚舉
# ============================================================

class GameStatus(str, Enum):
    """遊戲狀態"""
    PENDING = "pending"           # 等待投注
    IN_PROGRESS = "inProgress"   # 進行中
    PLAYER_BUST = "playerBust"   # 玩家爆牌
    DEALER_BUST = "dealerBust"   # 莊家爆牌
    PLAYER_WIN = "playerWin"     # 玩家勝利
    DEALER_WIN = "dealerWin"     # 莊家勝利
    PUSH = "push"                 # 平局
    BLACKJACK = "blackjack"       # Blackjack
    INSURANCE_WIN = "insuranceWin"
    INSURANCE_LOSE = "insuranceLose"


class GameAction(str, Enum):
    """可用操作 (用於介面與決策)"""
    HIT = "hit"
    STAND = "stand"
    DOUBLE = "double"
    SPLIT = "split"
    INSURANCE = "insurance"
    NO_INSURANCE = "noInsurance"



# ============================================================
# 牌面計算工具
# ============================================================

CARD_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5,
    "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "J": 10, "Q": 10, "K": 10,
    "A": 11,
}

CARD_SUIT_MAP = {"H": "♥", "D": "♦", "C": "♣", "S": "♠"}


def card_to_str(card_obj: dict) -> str:
    """將 API 的卡牌物件轉換為內部格式 rank+suit，例如 {'rank': 'A', 'suit': 'H'} -> 'AH'"""
    rank = card_obj.get("rank", "?")
    suit = card_obj.get("suit", "?").upper()
    return f"{rank}{suit}"


def parse_card(card_str: str) -> tuple[str, str]:
    """
    解析內部牌面字串，例如 'AH' -> ('A', '♥')
    """
    if len(card_str) < 2:
        return ("?", "?")
    
    # 處理 '10H' 這種情況
    if card_str.startswith("10"):
        rank = "10"
        suit = card_str[2:].upper()
    else:
        rank = card_str[0].upper()
        suit = card_str[1:].upper()
        
    return (rank, CARD_SUIT_MAP.get(suit, suit))


def card_display(card_str: str) -> str:
    """顯示牌面，例如 'AH' -> 'A♥'"""
    rank, suit = parse_card(card_str)
    return f"{rank}{suit}"


def hand_value(cards: list[str]) -> int:
    """
    計算手牌點數，自動處理 Ace 的值 (1 或 11)
    """
    total = 0
    aces = 0

    for card in cards:
        if not card:
            continue
        
        if card.startswith("10"):
            rank = "10"
        else:
            rank = card[0].upper()
            
        value = CARD_VALUES.get(rank, 0)
        if rank == "A":
            aces += 1
        total += value

    # 如果點數超過 21，把 Ace 改為 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1

    return total


def is_soft_hand(cards: list[str]) -> bool:
    """判斷是否為軟牌（含 Ace 且 Ace 算 11）"""
    total = 0
    aces = 0
    for c in cards:
        if not c: continue
        rank = "10" if c.startswith("10") else c[0].upper()
        total += CARD_VALUES.get(rank, 0)
        if rank == "A": aces += 1
    
    return aces > 0 and total <= 21


def is_pair(cards: list[str]) -> bool:
    """判斷是否可以分牌（兩張相同點數）"""
    if len(cards) != 2:
        return False
    r1 = "10" if cards[0].startswith("10") else cards[0][0].upper()
    r2 = "10" if cards[1].startswith("10") else cards[1][0].upper()
    v1 = CARD_VALUES.get(r1, 0)
    v2 = CARD_VALUES.get(r2, 0)
    return v1 == v2


def is_blackjack(cards: list[str]) -> bool:
    """判斷是否為 Blackjack（Ace + 10點牌）"""
    if len(cards) != 2:
        return False
    return hand_value(cards) == 21


# ============================================================
# 資料模型
# ============================================================

@dataclass
class BlackjackState:
    """BlackJack 遊戲當前狀態"""
    player_cards: list[str] = field(default_factory=list)
    dealer_cards: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    active: bool = True
    insurance_available: bool = False
    identifier: Optional[str] = None

    @property
    def player_total(self) -> int:
        return hand_value(self.player_cards)

    @property
    def dealer_total(self) -> int:
        return hand_value(self.dealer_cards)

    @property
    def dealer_upcard(self) -> Optional[str]:
        """莊家明牌（第一張）"""
        return self.dealer_cards[0] if self.dealer_cards else None

    @property
    def dealer_upcard_value(self) -> int:
        """莊家明牌點數"""
        if not self.dealer_upcard:
            return 0
        rank = "10" if self.dealer_upcard.startswith("10") else self.dealer_upcard[0].upper()
        return CARD_VALUES.get(rank, 0)

    @property
    def is_soft(self) -> bool:
        return is_soft_hand(self.player_cards)

    @property
    def is_finished(self) -> bool:
        return not self.active

    @property
    def can_split(self) -> bool:
        return GameAction.SPLIT in self.actions or "split" in self.actions

    @property
    def can_double(self) -> bool:
        return GameAction.DOUBLE in self.actions or "double" in self.actions

    @property
    def can_insurance(self) -> bool:
        return self.insurance_available or "insurance" in self.actions

    def display_player_hand(self) -> str:
        cards = " ".join(card_display(c) for c in self.player_cards)
        return f"{cards} (點數: {self.player_total}{'s' if self.is_soft else ''})"

    def display_dealer_hand(self) -> str:
        if not self.dealer_cards:
            return "無牌"
        cards = " ".join(card_display(c) for c in self.dealer_cards)
        return f"{cards} (點數: {self.dealer_total})"

    @classmethod
    def from_api_response(cls, state_data: dict, active: bool = True) -> "BlackjackState":
        """從 API 回應建立遊戲狀態 (支援新版嵌套結構)"""
        player_list = state_data.get("player", [])
        dealer_list = state_data.get("dealer", [])
        
        player_hand = player_list[0] if player_list else {}
        dealer_hand = dealer_list[0] if dealer_list else {}
        
        player_cards = [card_to_str(c) for c in player_hand.get("cards", [])]
        dealer_cards = [card_to_str(c) for c in dealer_hand.get("cards", [])]
        
        # 修正：actions 現在位於 player 手牌物件內
        actions = player_hand.get("actions", [])
        identifier = state_data.get("identifier") or player_hand.get("id")
        
        return cls(
            player_cards=player_cards,
            dealer_cards=dealer_cards,
            actions=actions,
            active=active,
            insurance_available=player_hand.get("insuranceAvailable", False),
            identifier=identifier
        )


@dataclass
class BetResult:
    """投注結果"""
    game_id: str
    active: bool
    payout: float
    payout_multiplier: float
    currency: str
    amount: float
    state: Optional[BlackjackState] = None
    balance: float = 0.0

    @property
    def profit(self) -> float:
        return self.payout - self.amount if not self.active else 0.0

    @property
    def is_win(self) -> bool:
        if self.active: return False
        return self.payout_multiplier > 1.0

    @property
    def is_push(self) -> bool:
        if self.active: return False
        return self.payout_multiplier == 1.0

    @property
    def is_loss(self) -> bool:
        if self.active: return False
        return self.payout_multiplier < 1.0

    def display_result(self) -> str:
        if self.active:
            return f"🔵 遊戲進行中"
        if self.is_win:
            return f"✅ 勝利 +{self.payout - self.amount:.8f} (x{self.payout_multiplier})"
        elif self.is_push:
            return f"🟡 平局"
        else:
            return f"❌ 失敗 -{self.amount:.8f}"

    @classmethod
    def from_api_response(cls, data: dict, key: str = "blackjackBet") -> "BetResult":
        """從 API 回應建立投注結果"""
        game = data.get(key, {})
        if not game and "blackjackNext" in data:
            game = data.get("blackjackNext", {})
            
        state_data = game.get("state", {})
        active = game.get("active", False)

        balance = 0.0
        user = game.get("user", {})
        balances = user.get("balances", [])
        
        for b in balances:
            avail = b.get("available", {})
            if avail and float(avail.get("amount", 0)) > 0:
                balance = float(avail.get("amount", 0))
                break

        return cls(
            game_id=game.get("id", ""),
            active=active,
            payout=float(game.get("payout", 0)) if game.get("payout") is not None else 0.0,
            payout_multiplier=float(game.get("payoutMultiplier", 0)) if game.get("payoutMultiplier") is not None else 0.0,
            currency=game.get("currency", "usdt"),
            amount=float(game.get("amount", 0)) if game.get("amount") is not None else 0.0,
            state=BlackjackState.from_api_response(state_data, active=active) if state_data else None,
            balance=balance,
        )


@dataclass
class SessionStats:
    """本次會話統計"""
    total_rounds: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    blackjacks: int = 0
    total_wagered: float = 0.0
    total_payout: float = 0.0
    start_balance: float = 0.0
    current_balance: float = 0.0

    @property
    def profit(self) -> float:
        return self.total_payout - self.total_wagered

    @property
    def win_rate(self) -> float:
        if self.total_rounds == 0:
            return 0.0
        return self.wins / self.total_rounds * 100

    @property
    def net_pnl(self) -> float:
        return self.current_balance - self.start_balance
