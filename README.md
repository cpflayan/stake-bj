# ♠️ Stake Blackjack Auto-Bet Bot

> **警告：**  
> 本工具僅供學習和研究目的。使用自動化機器人可能違反 Stake.com 使用條款。使用前請自行評估風險。

---

## 🏗️ 架構概覽（基於 webdice bot 設計）

```
stake-bj/
├── stake_bj/
│   ├── client.py          # GraphQL API 客戶端（HTTP + 重試邏輯）
│   ├── graphql_queries.py # 所有 Mutation/Query 定義
│   ├── models.py          # 資料模型（牌面計算、遊戲狀態）
│   ├── strategy.py        # 基本策略 + Martingale 投注策略
│   ├── validator.py       # 客戶端驗證（設定 + Token + 餘額）
│   ├── engine.py          # 核心遊戲引擎（主循環）
│   └── main.py            # CLI 進入點
├── tests/
│   └── test_blackjack.py  # 單元測試 (49 個測試)
├── .env.example           # 環境變數範本
└── pyproject.toml
```

---

## 🚀 快速開始

### 1. 複製設定檔

```bash
cp .env.example .env
```

### ### 2. 取得連線資訊 (重要)

為了跳過驗證，機器人需要模擬你的瀏覽器環境，請依照以下步驟取得設定值：

1. 在瀏覽器開啟 `https://stake.com` 並登入。
2. 按下 `F12` 開啟開發者工具，點選 **Network (網路)** 分頁。
3. 重新整理頁面 (F5)，在左側清單找到一個名為 `graphql` 的請求。
4. 點擊該請求，在右側標頭 (Headers) 往下捲動找到 **Request Headers**：
   - **STAKE_TOKEN**: 尋找 `x-access-token` 標頭的值，或是 `cookie` 裡面的 `session` 值。
   - **COOKIE**: 直接複製整段 `cookie:` 標頭的內容。
   - **USER_AGENT**: 直接複製整段 `user-agent:` 標頭的內容。
5. 將這些值填入 `.env` 檔案對應位置。

### 3. 調整投注設定（`.env`）

```bash
BET_AMOUNT=0.00000001      # 基礎投注額
STOP_PROFIT=0.001          # 停利金額
STOP_LOSS=0.001            # 停損金額
STRATEGY=flat              # 投注策略: flat | martingale
MAX_ROUNDS=100             # 最大局數 (0=無限)
```

### 4. 執行

```bash
uv run stake-bj
# 或
uv run python -m stake_bj.main
```

---

## 🃏 BlackJack 操作元件

| 操作 | GraphQL Mutation | 說明 |
|------|-----------------|------|
| 投注 | `blackjackBet` | 開始新一局，設定金額和幣種 |
| 叫牌 | `blackjackHit` | 要求發一張牌 |
| 停叫 | `blackjackStand` | 結束回合，讓莊家出牌 |
| 加倍 | `blackjackDouble` | 加倍投注，只再拿一張牌 |
| 分牌 | `blackjackSplit` | 將對子分成兩手 |
| 保險 | `blackjackInsurance` | 莊家 Ace 時購買保險 |

---

## 📊 基本策略（Basic Strategy）

實作數學最優決策表，基於 6 副牌、莊家 Soft 17 停叫規則：

### 策略決策優先順序

```
1. 保險（預設關閉，數學不建議）
2. 分牌（Pair Strategy Table）
3. 軟牌（Soft Totals Table，含 Ace）
4. 硬牌（Hard Totals Table）
```

### 關鍵決策示例

| 玩家手牌 | 莊家明牌 | 動作 |
|---------|---------|------|
| 11 | 2-10 | 加倍 |
| 16 | 7+ | 叫牌 |
| 16 | 2-6 | 停叫 |
| A+7 (Soft 18) | 3-6 | 加倍 |
| A+7 (Soft 18) | 7-8 | 停叫 |
| A+7 (Soft 18) | 9,10,A | 叫牌 |
| A-A | 任何 | 分牌 |
| 8-8 | 任何 | 分牌 |
| T-T | 任何 | 停叫（不分） |

---

## 💰 投注策略

### Flat（平注）

```
每局固定投注 BET_AMOUNT，不因輸贏改變
```

### Martingale（馬丁格爾）

```
輸了：下注加倍（BET × MARTINGALE_MULTIPLIER）
贏了：重置回基礎投注額
設定上限：MAX_MARTINGALE_STEPS（防止無限加倍）
```

⚠️ **風險警告：** Martingale 在連敗時可能迅速消耗資金

---

## ✅ 客戶端驗證

啟動前自動執行以下驗證：

1. **本地設定驗證**
   - Token 格式檢查
   - 投注金額範圍檢查
   - 停損停利合理性
   - Martingale 最壞情況估算
   - 貨幣類型支援確認

2. **線上 Token 驗證**
   - 向 Stake API 驗證 Token 有效性
   - 取得使用者帳號資訊

3. **餘額驗證**
   - 確認帳號餘額足夠 10 局

---

## 🧪 執行測試

```bash
uv run pytest tests/ -v
```

測試覆蓋範圍（49 個測試）：

- 牌面計算（Ace 自動調整）
- 基本策略（硬牌/軟牌/分牌）
- Martingale 投注策略
- 客戶端設定驗證
- 遊戲狀態模型

---

## 🔧 進階設定

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `BET_DELAY` | `1.0` | 局間延遲（秒），避免頻率限制 |
| `USE_INSURANCE` | `false` | 是否啟用保險（數學上不建議） |
| `LOG_LEVEL` | `INFO` | 日誌等級: DEBUG/INFO/WARNING |
| `LOG_FILE` | `` | 日誌存檔路徑（空=不存檔） |
| `CURRENCY` | `usd` | 幣種 |

---

## ⚠️ 使用注意事項

1. **從最小投注開始** 測試 Token 是否正常運作
2. **設定合理停損** 避免超出預期損失
3. **不要使用 Martingale** 除非你了解其數學風險
4. **基本策略不保證獲利**，只是最優化長期期望值
5. Stake.com 的 Blackjack 有 **莊家優勢約 0.5%**（基本策略之後）
