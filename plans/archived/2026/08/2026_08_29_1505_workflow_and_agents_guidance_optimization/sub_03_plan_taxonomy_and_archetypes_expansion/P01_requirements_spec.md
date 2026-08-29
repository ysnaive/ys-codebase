# 需求規格說明書 (Requirements Specification)

> 功能名稱：計畫分流維度重構、工作類型拓撲擴充與策略資產規範 (Plan Taxonomy, Archetypes & Strategic Assets)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **Fast Track 4 維度綜合判定矩陣** | 於 `DevelopmentStandards.md` 與 `AgentsStandards.md` 重構 Fast Track 判定條件：① 預估總修改行數 $\le 100$ 行；② Public API 契約 0 變更；③ 零跨模組新依賴與結構變更；④ 既有測試 100% 可守門驗證。 | P0 | `[P00:DR-01]` |
| **FR-02** | **Fast Track 動態升級閘門 (Escalation Gate)** | 於標準規範中明訂：若在 Fast Track 規劃 (FT-1) 或實作 (FT-2) 發現超出 100 行或需變更 Public API，Agent 必須強制停手呈報升級為 Full Track。 | P0 | `[P00:DR-01]` |
| **FR-03** | **Umbrella 主計畫雙軌拓撲規範** | 於 `umbrella_overview.md` 模板與標準規範確立：模式 B-1（預先規劃型 Pre-planned 藍圖型）與模式 B-2（增量演進型 Incremental 滾動型），兩者均由開發者實機驗收後評估收斂。 | P0 | `[P00:DR-02]` |
| **FR-04** | **修訂計畫 (Revision Plan) 流程規範** | 於標準規範與工作流正式確立「修訂計畫」為一等公民：免除 P00~P07 完整生命週期，採「精準定位 ➔ 原地極小修訂 ➔ 極簡變更卡 ➔ Turn Gate 待命」4 步短循環。 | P0 | `[P00:DR-03]` |
| **FR-05** | **調研計畫 (Research Plan) 3 步生命週期** | 於標準規範正式確立「調研計畫」為一等公民：採 `P00_discuss` ➔ `R01_{topic}.md` ➔ 調研結案三大出口（立項開發 / 轉入 Roadmap / 存檔歸檔），100% 免除代碼實作與測試文件負擔。 | P0 | `[P00:DR-04]` |
| **FR-06** | **Roadmap 策略資產協議與標準模板** | 1. 於 `contributes` 定義 `workflow.roadmap://`（模板預設 `!undefined`，init 預設解析為 `workflow.plans://roadmap/`）。<br/>2. 建立標準模板 `assets/templates/roadmap.md`（含 Header 元數據、問題背景與量化分析、方案對比、SOP、實施路線）。 | P0 | `[P00:DR-05]` |
| **FR-07** | **CLI 指令 `agents-workflow roadmap` 實作** | 擴充 `agents-workflow` CLI，支援 `roadmap` 指令條列 `workflow.plans://roadmap/*.md` 之 Header 元數據與問題背景摘要，大幅降低 Agent 讀檔負擔。 | P0 | `[P00:DR-05]` |
| **FR-08** | **`/Roadmap` 智能推薦工作流** | 新增 `assets/workflows/Roadmap.md` 工作流，引導 Agent 自動呼叫 `roadmap` CLI 條列並主動依專案現況推薦合適主題。 | P1 | `[P00:DR-05]` |
| **FR-09** | **原 P00 改名為 `P00_discuss` 與顧問角色純化** | 1. 模板 `P00_semantic_requirements.md` 更名為 `P00_discuss.md`。<br/>2. 標準規範明訂顧問角色紀律：除開發者主動要求外絕不主動提個人主觀想法，僅以客觀事實與技術角度回覆。 | P0 | `[P00:DR-06]` |
| **FR-10** | **`/NewPlan` 延遲建檔機制與 JIT 分流引導** | 1. 更新 `NewPlan.md`：觸發時不立即建實體目錄，先於對話討論，待確定分流時才一併建立目錄與填入對應模板。<br/>2. 建立全景 6 大分支判斷矩陣，明確符合時適時建議分流，禁止 Agent 自行切換。 | P0 | `[P00:DR-07]`, `[P00:DR-08]` |
| **FR-11** | **長對話防呆阻斷與調研無痛升級鏈** | 1. P00_discuss 討論過長時主動建議轉入調研計畫。<br/>2. 調研計畫結案後可 100% 無縫升級為實作型 Plan（直接繼承 R01 結論）。 | P0 | `[P00:DR-09]` |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **Fast Track 實作中規模失控膨脹** | 實作中若發現總行數將超出 100 行或必須調整 Public API 簽名，Agent 必須強制停止實作，向開發者呈報升級為 Full Track。 |
| **EC-02** | **`/NewPlan` 討論中途放棄或中斷** | 由於採用延遲建檔機制，對話中斷時磁碟上 0 殘留空目錄，完全不產生垃圾計畫檔案。 |
| **EC-03** | **Roadmap 目錄不存在或為空** | 執行 `agents-workflow roadmap` 或 `/Roadmap` 時若無檔案，友好輸出「目前無待啟動之 Roadmap 技術儲備」，安全返回 0。 |
| **EC-04** | **非標準格式之 Roadmap 檔案** | 解析器具備強韌容錯機制，若缺少特定 Header 欄位則自動 fallback 至檔名與前 3 行文字預覽，不崩潰報錯。 |
| **EC-05** | **調研計畫無痛升級為實作計畫** | 升級時保留原 `P00_discuss.md` 與 `R01_*.md`，直接於同一計畫目錄下追加 `P01_requirements_spec.md` 繼續推進，歷史 100% 剛性繼承。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **回歸與自引用相容** | 全生態系 209/209 測試 100% Passed，新增 CLI 指令與模板 100% 通過 `plan verify` 與編譯物化。 |
| **NFR-02** | **Token 與 IO 效率** | 延遲建檔消除無效磁碟寫入；CLI `roadmap` 結構化摘要過濾，節省 Agent 80%+ 的無效檔案讀取與上下文消耗。 |
| **NFR-03** | **模板結構與註解純淨度** | 所有產出模板落檔時 100% 徹底剝除 HTML 導引註解，符合 CommonMark 標準規範。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]` [DN-AW-03] 統一靜態資產空間收納至 `assets/`**：
  所有新增的模板（`roadmap.md`、`P00_discuss.md`）與工作流（`Roadmap.md`）必須 100% 收納於 `ys_codebase/source/agents-workflow/assets/` 結構下。
- **`[!IMPORTANT]` [DN-AW-08] Stage 2 佔位符二分法解析**：
  在新增工作流中若有指向專案根目錄的檔案指引，必須遵循 `__${...}__` 協議，以確保編譯物化後 100% 根目錄直達且無反引號殘留。
