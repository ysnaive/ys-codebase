# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：計畫分流維度重構、工作類型拓撲擴充與策略資產規範 (Plan Taxonomy, Archetypes & Strategic Assets)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-11 在架構與 API 規格中 100% 具體承接（Fast Track 4 維度、Umbrella 雙軌、修訂計畫、調研計畫、Roadmap 體系、P00_discuss 顧問紀律、延遲建檔、JIT 動態引導與調研無痛升級）。
- [x] **邊界防護**：EC-01 ~ EC-05 在 `RoadmapManager` 與標準規範中均有具體防禦與 fallback 策略。
- [x] **依賴純淨**：`RoadmapManager` 零外部依賴，符合 NFR-01 與 NFR-02 指標約束。
- [x] **佔位符二次確認**：Markdown 超連結 100% 採用 `__#{uri}__`；根目錄路徑/指令 100% 採用 `__${uri}__`；`PHASE00_HEADER`/`AGENTS_GUILD`/`TEMPLATE` 100% 無損繼承既有標準命名。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1 (概覽)** | `docs/agents-workflow/README.md` | Modify | 增補 Roadmap 策略資產體系、CLI `roadmap` 指令、`/Roadmap` 工作流與 6 大計畫分支總覽。 |
| **維度 4 (規格)** | `docs/agents-workflow/contributes.format.md` | Modify | 記錄 `workflow.roadmap://` 協議與新增 token 錨點規範。 |
| **維度 7 (標準)** | `docs/agents-workflow/STANDARDS.md` | Modify | 同步 4 維度 Fast Track 判定矩陣、Umbrella 雙軌拓撲與顧問角色紀律。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當 `plans/roadmap/` 目錄中混雜了非標準 Header、檔名異常或包含二進位檔案時，`RoadmapManager` 是否會引發解析崩潰或 IO 阻塞？  
> 💡 **防護解法**：`RoadmapManager` 嚴格僅掃描 `.md` 副檔名；採用安全的 line-by-line 正則匹配與 UTF-8 (replace) 串流讀取，若無合規 Header 則自動以檔名與前 3 行文字截斷作為預覽 (EC-04)，100% 杜絕解析崩潰。

> ❓ **尖銳問題 2**：`/NewPlan` 實施延遲建檔後，若開發者在 P00_discuss 討論途中切換話題或放棄計畫，是否會在磁碟上留下垃圾檔案？  
> 💡 **防護解法**：延遲建檔機制保證在開發者「明確確認計畫類型並指示進入」之前，實體磁碟維持 0 寫入 (EC-02)。對話中止時不會有任何空目錄或未定稿文件沉澱於磁碟。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (基礎協議與 Contributes 定義)**：
  - 更新 `source/agents-workflow/contributes/core.json`（註冊 `workflow.roadmap` 協議與 `roadmap` CLI command）。
  - 更新 `source/agents-workflow/contributes/agents-workflow.json`（註冊新 export、token 與模板更名指向）。
- [ ] **TASK-02 (核心 SDK 與 CLI 工具實作)**：
  - 實作 `source/agents-workflow/agents_workflow/roadmap.py` (`RoadmapItem`, `RoadmapManager`)。
  - 實作 `source/agents-workflow/scripts/cli.py` (`cmd_roadmap` 子指令分發)。
- [ ] **TASK-03 (模板資產重構與新增)**：
  - 建立 `source/agents-workflow/assets/templates/P00_discuss.md`（更名與顧問純化）。
  - 建立 `source/agents-workflow/assets/templates/roadmap.md`（標準技術路線圖模板）。
  - 更新 `source/agents-workflow/assets/templates/umbrella_overview.md`（模式 B-1 vs B-2 標頭）。
- [ ] **TASK-04 (工作流導引與標準手冊演進)**：
  - 建立 `source/agents-workflow/assets/workflows/Roadmap.md`（`/Roadmap` 智能推薦工作流）。
  - 更新 `source/agents-workflow/assets/workflows/NewPlan.md`（延遲建檔、JIT 分流引導、長對話調研阻斷）。
  - 更新 `source/agents-workflow/assets/standards/DevelopmentStandards.md`（4 維度 Fast Track / Umbrella 雙軌 / 修訂計畫 / 調研 3 步 SOP / Roadmap 協議）。
  - 更新 `source/agents-workflow/assets/standards/AgentsStandards.md`（P00_discuss 顧問紀律、JIT 分流守門與延遲建檔鐵律）。
- [ ] **TASK-05 (測試套件更新與全量迴歸驗證)**：
  - 於 `test/test_agents_workflow.py` 新增 Roadmap CLI、RoadmapManager 容錯與模板合規性測試。
  - 實機執行 `python test/run_regression.py` 驗證全生態系 100% Passed。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 依序閉環交付**：各任務嚴格依照 TASK-01 ➔ TASK-05 依賴拓撲順序實作，確保底層協議先於上層模板，模板先於工作流。
- **[P04:DR-02] Test-First 剛性定稿**：同步審查並將 [P06_test_plan.md](./P06_test_plan.md) 標記為 `Confirmed`。
