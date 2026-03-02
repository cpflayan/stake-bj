"""
Stake.com Blackjack GraphQL 查詢和 Mutation 定義
更新為 2024+ 最小化結構，確保相容性
修正：actions 與 insuranceAvailable 位於 player 手牌物件內
"""

BLACKJACK_BET = """
mutation BlackjackBet($amount: Float!, $currency: CurrencyEnum!) {
  blackjackBet(amount: $amount, currency: $currency) {
    id
    active
    payout
    payoutMultiplier
    amount
    state {
      ... on CasinoGameBlackjack {
        player { 
          cards { rank suit }
          actions
        }
        dealer { cards { rank suit } }
      }
    }
  }
}
"""

BLACKJACK_NEXT = """
mutation BlackjackNext($action: BlackjackNextActionInput!, $identifier: String) {
  blackjackNext(action: $action, identifier: $identifier) {
    id
    active
    payout
    payoutMultiplier
    amount
    state {
      ... on CasinoGameBlackjack {
        player { 
          cards { rank suit }
          actions
        }
        dealer { cards { rank suit } }
      }
    }
  }
}
"""

USER_BALANCE = """
query UserBalance {
  user {
    id
    name
    balances {
      available {
        amount
        currency
      }
    }
  }
}
"""

ACTIVE_BLACKJACK = """
query ActiveBlackjack {
  user {
    activeCasinoBets {
      id
      active
      game
      payout
      payoutMultiplier
      amount
      state {
        __typename
        ... on CasinoGameBlackjack {
          player { 
            cards { rank suit }
            actions
          }
          dealer { 
            cards { rank suit }
          }
        }
      }
    }
  }
}
"""
