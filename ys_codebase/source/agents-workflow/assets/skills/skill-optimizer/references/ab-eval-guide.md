# A/B 基準測試與觸發評測指南 (Mode B Closing Guide)

## 目錄 (Contents)

- [模式 B 收尾操作總覽](#模式-b-收尾操作總覽)
- [步驟一：設計觸發率測試集 (`trigger_evals.json`)](#步驟一設計觸發率測試集-trigger_evalsjson)
- [步驟二：訓練／驗證集切分與防過擬合迴圈](#步驟二訓練驗證集切分與防過擬合迴圈)
- [步驟三：設計功能型 A/B 測試案例 (`evals/evals.json`)](#步驟三設計功能型-ab-測試案例-evalsevalsjson)
- [步驟四：執行舊版 (`old_skill`) 與新版 (`with_skill`) 對照測試](#步驟四執行舊版-old_skill-與新版-with_skill-對照測試)
- [步驟五：評分斷言與彙整基準報告 (`benchmark.json`)](#步驟五評分斷言與彙整基準報告-benchmarkjson)

當開發者於階段一選擇**模式 B（靜態重構 ＋ A/B 基準測試集）**時，請在**階段四（分支 B）**依據本指南產出評測檔案並執行基準比對。

---

## 模式 B 收尾操作總覽

優化既有 Skill 時，A/B 測試的目標是透過量化數據證明新版（`with_skill`）相較於舊版快照（`old_skill`）在以下兩方面有所提升且**零功能退化**：

1. **觸發精準度（Trigger Accuracy）**：新版 `description` 能在目標任務（包含顯式 `/cmd` 與隱性口語意圖）穩定觸發，同時在共用關鍵字的相鄰技能干擾題（Near-misses）保持不誤觸發。
2. **執行品質與結構合規度（Quality & Compliance Delta）**：新版 `SKILL.md` 能提高客觀斷言通過率（如檢核表遵循、狀態卡節流、既有連結與佔位符無損保留），並維持精簡的 Token 消耗。

---

## 步驟一：設計觸發率測試集 (`trigger_evals.json`)

建立包含正向題（`should_trigger: true`）與近似負向題（`should_trigger: false`）的 `evals/trigger_evals.json`：

```json
[
  {
    "id": "trig-continue-01",
    "target_skill": "continue",
    "split": "train",
    "query": "幫我接續上次做到一半的那個功能計畫，看看 handoff.md 寫到哪",
    "should_trigger": true,
    "rationale": "直接命中 continue 技能之 handoff 現場恢復核心功能"
  },
  {
    "id": "trig-continue-02",
    "target_skill": "continue",
    "split": "validation",
    "query": "我有一個全新的快取優化需求想要立項開新計畫，幫我評估要走哪種開發模式",
    "should_trigger": false,
    "rationale": "近似負向題 (Near-miss) - 雖提到計畫，但屬於開立新計畫，應觸發 new-plan 而非 continue"
  }
]
```

**高鑑別度觸發測試集設計原則**：

- **正向題需涵蓋顯性與隱性口語提問**：混合直接點名指令與僅描述工作情境的自然語言提問。
- **負向題必須採用相鄰技能干擾項（Near-misses）**：每一題 `should_trigger: false` 都必須與目標技能共用領域詞彙（如「計畫」、「文檔」、「測試」），但實際應路由至另一個相鄰技能（例如測試 `documentation` 時，以「更新開發計畫內的架構草案」作為負向題）。

---

## 步驟二：訓練／驗證集切分與防過擬合迴圈

1. **固定 60/40 切分比例**：將測試題隨機抽取 60% 標記為 `"split": "train"`（訓練集），40% 標記為 `"split": "validation"`（驗證集）。
2. **多次執行計算觸發率（Trigger Rate）**：
   - 正向題（`should_trigger: true`）觸發率 `>= 0.67` 視為通過。
   - 負向題（`should_trigger: false`）觸發率 `<= 0.33` 視為通過。
3. **防過擬合（Anti-Overfitting）修正守則**：
   - 僅根據 `train` 訓練集失敗案例調整 `description` 的概念邊界，嚴禁將測試題字面原話硬塞入 `description`。

---

## 步驟三：設計功能型 A/B 測試案例 (`evals/evals.json`)

針對技能本體的執行品質與不變量（Invariants），建立具客觀斷言（Assertions）的 `evals/evals.json`：

```json
{
  "suite_name": "skills-ab-eval",
  "evals": [
    {
      "id": 1,
      "skill_name": "auto",
      "name": "eval-auto-p06-gate",
      "prompt": "目前計畫處於 P00 Confirmed，請幫我執行 /auto 自動推進",
      "expected_output": "依序產出 P01~P05 並執行 P06 自動化測試，抵達 P06 手動/UX 驗收點時必須輸出極簡卡片並強制 End Turn，不可自行進入 P07",
      "assertions": [
        "完整保留所有跨檔案連結與動態路徑佔位符",
        "明確包含 Phase 01 至 Phase 05 連續產出與 changelog.md 同步規則",
        "抵達 P06 後強制輸出極簡狀態卡並 End Turn，嚴禁自行標記 Completed 或進入 Phase 07"
      ]
    }
  ]
}
```

---

## 步驟四：執行舊版 (`old_skill`) 與新版 (`with_skill`) 對照測試

1. 在獨立子代理（Subagent）或驗證腳本中，分別對舊版快照（`old_skill`）與重構版（`with_skill`）執行靜態合規與模擬任務評測。
2. 記錄每項測試的斷言通過率（`pass_rate`）、行數／Token 數（`tokens`）與動態佔位符／連結保留率（`placeholder_preservation_rate`）。

---

## 步驟五：評分斷言與彙整基準報告 (`benchmark.json`)

將新舊版比對結果輸出為 `evals/benchmark.json`，確認：

- **既有佔位符與核心功能保留率 = 100%**（零功能退化）。
- **正負向觸發邊界識別率與結構合規率顯著提升**。

