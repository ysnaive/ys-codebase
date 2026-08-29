# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：計畫分流維度重構、工作類型拓撲擴充與策略資產規範 (Plan Taxonomy, Archetypes & Strategic Assets)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Confirmed  
> 計畫類型：Architecture  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  目前計畫體系僅硬性分為「迅捷開發」、「標準開發」與「階段式開發 (分類型主計畫)」，在實務執行時面臨 5 大核心盲點與結構性缺口：
  1. **迅捷開發 (Fast Track) 評定標準過於硬性**：不應單純硬性限制檔案修改數（如 $\le 2$），應改為評估「修改規模與語意風險」（例如 10 個檔案各改 5 行型別命名 vs 1 個檔案重寫 2000 行核心邏輯，現有規則存在盲點）。
  2. **分類型主計畫 (Umbrella) 缺乏二分法細分**：實務上分為「預先規劃型 (Pre-planned：高聚合主題、分階段推進)」與「增量演進型 (Incremental：同維度優化、邊做邊衍生後續子計畫)」，現有模板未加以區分。
  3. **缺少純粹增量型 / 即時交互型修改工作流**：例如文檔校閱或零散修訂，開發者邊看邊提意見，最佳方式是即刻對照事實、及時原地修改，若強行走標準 P00~P07 會導致 context 嚴重膨脹且效率低下。應將其正式列為一種計畫類型「修訂計畫 (Revision Plan)」。
  4. **缺少純粹調研/非代碼計畫類型**：技術調研、發想、測評等非代碼需求缺少一等公民的計畫規範與輕量 SOP。
  5. **缺少非過程計畫的長期策略資產格式**：缺少非過程性（`plans/`）、非標準代碼文檔（`docs/`）的長期策略資產規範（如 `roadmap/` 長期里程碑與技術儲備）。

- **標準流程演進需求**：
  1. **原 P00 改名為 `P00_discuss`**：語意改為與開發者進行本計畫之開放討論，內容不限、零臆測。除開發者主動要求發想外，Agent 絕不主動提出想法，僅以客觀事實與技術架構角度回覆。
  2. **重構全景計畫類型判斷矩陣**：涵蓋所有 6 大計畫分支（Full Track、Fast Track、Umbrella Pre-planned、Umbrella Incremental、Revision Plan、Research Plan）。
  3. **JIT 動態分流引導守門**：P00 討論時，Agent 時刻比對矩陣，當已明確符合某類型時可適時建議「是否進入 XX 計畫」，但**絕對禁止 Agent 自行進入，必須由開發者確認或主動指定**。
  4. **`/NewPlan` 延遲建檔機制**：`/NewPlan` 不再立即建立實體目錄與檔案，待確立計畫類型時才一併建立並填入對應模板。
  5. **長對話防呆阻斷 ➔ 調研計畫無痛升級**：討論過長或技術不確定性高時主動建議進入調研計畫，調研結案後可無痛無縫升級為實作型計畫。

- **邊界排除 (Explicitly Excluded)**：
  - 本次不更動 `core`、`dev` 或 `knowledge-db` 底層引擎的代碼邏輯，僅聚焦於 `agents-workflow` 的資產、標準規範（`DevelopmentStandards.md`、`AgentsStandards.md`）、工作流（`workflows/`）、CLI 指令與模板（`templates/`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 迅捷開發 (Fast Track / Level 0) 4 維度判定矩陣與動態升級機制**：
  - 判定維度由單純的「檔案數 $\le 2$」升級為「**4 維度綜合規模與風險矩陣**」（必須 100% 同時滿足）：
    1. **修改規模 (Scale)**：預估總修改行數 $\le 100$ 行（不限檔案數，如批次重命名或常數替換均可；單檔若 $> 100$ 行或重構核心狀態機強制升級 Full Track）。
    2. **介面無損 (Non-breaking)**：Public API / 介面契約 / CLI 參數 100% 維持原樣。
    3. **架構自包含 (Self-contained)**：不引入新跨模組依賴、不更動核心資料結構/Schema。
    4. **驗證直接性 (Direct Verification)**：既有單元/回歸測試可直接 100% 守門驗證。
  - **動態升級閘門 (Escalation Gate)**：實作中若發現行數超出 100 行或涉及 API 變更，Agent 強制停止實作，向開發者呈報升級至 Full Track。

- **[P00:DR-02] 分類型主計畫 (Umbrella / Level 2) 雙軌拓撲二分法**：
  - **模式 B-1 (預先規劃型 Pre-planned Staged Umbrella)**：
    - 適用：大型系統重構、多階段已知里程碑、主題高聚合產物。
    - 特性：立項時於 `umbrella_overview.md` 預排 `sub_01` ~ `sub_0N` 藍圖，但**保持彈性調整**，允許動態插入修復子計畫與範疇微調，最終結案一律由開發者實機驗收後評估收斂。
  - **模式 B-2 (增量演進型 Incremental Rolling Umbrella)**：
    - 適用：主題式持續優化、探索式改進。
    - 特性：以核心主題為錨點，後續子計畫隨前期成果與即時反饋動態衍生開立，由開發者評估收斂結案。

- **[P00:DR-03] 正式確立「修訂計畫 (Revision Plan)」作為一等公民計畫類型**：
  - 適用：文檔校閱、零散文案調整、代碼註解同步、邊驗證邊修訂之即時短循環。
  - 核心機制：免除傳統 P00~P07 完整儀式與大量文件負擔，採用「**即時定位 ➔ 原地極小修訂 ➔ 極簡變更卡呈遞 ➔ Turn Gate 待命**」的極短閉環，徹底杜絕 Token 浪費與 Context 膨脹。

- **[P00:DR-04] 正式確立「調研計畫 (Research Plan)」作為一等公民計畫類型**：
  - 適用：純技術選型、可行性調研、演算法評估、套件測評、架構發想對比。
  - 核心產物：以 `P00_discuss` (問題與維度) + `R01_{topic}.md` (深度技術報告/評估矩陣) + `changelog.md` 為核心，100% 免除 P01~P07 代碼與測試負擔。
  - **三大結案出口**：① 轉化為實作型 Plan（繼承 R01 結論）；② 沉澱為 Roadmap 技術儲備；③ 存檔歸檔至 `archived`。

- **[P00:DR-05] 長期策略資產 (Roadmap) 體系與工具鏈支援**：
  - **協議規範**：語意協議 `workflow.roadmap://` 在模板中預設為 `"!undefined"`，於專案 init 預設自啟動解析為 `"workflow.plans://roadmap/"`（實體路徑 `./plans/roadmap/`）。
  - **文檔標準**：設計標準 Roadmap 模板，移除僵化觸發條件，由開發者自主評估或透過工作流智能匹配。
  - **工作流支援**：新增 `/Roadmap` 工作流，Agent 自動閱讀當前 roadmap 庫並推薦適合當前專案情境的主題。
  - **CLI 指令支援**：提供 `python yscb.py agents-workflow roadmap`，條列各 roadmap header 元數據與問題背景量化分析摘要，大幅降低 Agent 讀檔 IO 與 Token 負擔。

- **[P00:DR-06] 原 P00 更名為 `P00_discuss` 與 Agent 顧問角色純化**：
  - 產物正式命名為 `P00_discuss.md`。
  - 語意調整為「與開發者進行本計畫之開放討論，內容不限、零臆測」。
  - 顧問紀律：除開發者主動要求發想或方案外，Agent 絕不主動提出個人主觀想法，僅以客觀事實、既有代碼與技術架構角度回覆與分析。

- **[P00:DR-07] `/NewPlan` 延遲建檔機制 (Delayed Plan Materialization)**：
  - `/NewPlan` 觸發時**不再立即於磁碟建立計畫資料夾與檔案**。
  - 先於對話中進行純粹的 P00_discuss 討論與需求脈絡釐清。
  - 待「確定計畫類型（開發者確認分流）」時，才一併建立實體計畫目錄並伴隨寫入對應模板檔案（如 Full Track 寫入 `P00_discuss.md`+`changelog.md`，Fast Track 寫入 `fast_track_plan.md` 等），徹底杜絕無效空目錄。

- **[P00:DR-08] 全景計畫類型判斷矩陣與 JIT 動態推薦 (Archetype Matrix & JIT Routing)**：
  - 建立覆蓋全 6 大類型的完整判斷矩陣（Full Track、Fast Track、Umbrella Pre-planned、Umbrella Incremental、Revision Plan、Research Plan）。
  - P00 討論過程中，Agent 時刻比對矩陣特徵。當需求已「明確」符合某類型時，Agent 可適時主動提出建議：「目前需求特徵符合 [XX 計畫類型]，請問是否進入該計畫？」，**絕對禁止 Agent 自行進入，必須由開發者確認或主動指定**。

- **[P00:DR-09] 長對話防呆阻斷與調研計畫無痛升級鏈 (Research Escalation & Seamless Transition)**：
  - 當 P00 討論過長、技術未知數過多或架構分歧較大時，Agent 主動建議先進入【調研計畫 (Research Plan)】。
  - 調研計畫結案產出 R01 後，可 100% 無縫升級轉化為標準開發 (Full Track) 或迅捷開發 (Fast Track)，直接繼承背景與結論，零摩擦銜接。

---

## 3. 開放議題與確認紀錄

- [x] 議題一：Fast Track 4 維度判定矩陣與動態升級機制已確認
- [x] 議題二：Umbrella 雙軌拓撲（Pre-planned 彈性藍圖 vs Incremental 滾動演進）已確認
- [x] 議題三：修訂計畫 (Revision Plan) 列入一等公民計畫類型已確認
- [x] 議題四：調研計畫 (Research Plan) 3 步生命週期與三大出口已確認
- [x] 議題五：Roadmap 協議 (`workflow.plans://roadmap/`)、模板、`/Roadmap` 工作流與 CLI `roadmap` 指令已確認
- [x] 流程補充一：P00 改名為 P00_discuss 與顧問角色純化已確認
- [x] 流程補充二：`/NewPlan` 延遲建檔機制已確認
- [x] 流程補充三：全景計畫類型判斷矩陣與 JIT 動態推薦守門已確認
- [x] 流程補充四：長對話防呆阻斷與調研計畫無痛升級鏈已確認
