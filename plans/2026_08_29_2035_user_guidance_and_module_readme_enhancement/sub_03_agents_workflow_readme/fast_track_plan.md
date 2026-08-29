# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：`sub_03_agents_workflow_readme`  
> 建立日期：2026-08-29  
> 所屬主計畫：`user_guidance_and_module_readme_enhancement`  
> 狀態：Completed  
> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.1  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求描述**：
  站在**純用戶與模組 Release 消費者視角**（在專案環境中執行 `python yscb.py install agents-workflow` 獲得 AI Agent 工作流與標準化協同體系的開發者），於模組源碼目錄撰寫 100% 自包含 (Self-Contained) 的 `agents-workflow` 模組導引手冊 [`source/agents-workflow/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/README.md)。
  涵蓋：
  1. **模組定位與架構全景**：AI Agent 協同標準化工作流框架、動態 Token 宣告式注入引擎、發布物工廠與計畫管理工具鏈。
  2. **核心工作流與 Slash Commands 導覽**：
     - `/ContextInit`：專案上下文熱啟動與規範加載
     - `/NewPlan`：標準開發作業流程（延遲建檔與 6 大分支矩陣）
     - `/Auto`：自動連續推進工作流（跳過中間 Checkpoint 連續執行至 P06 手動驗證）
     - `/Review`：開發完成後五維度品質審查與修復閉環
     - `/Retro`：開發歷程自檢與紀律合規評測
     - `/Discuss`：深度歸因、範疇保護與 5-Whys 根因分析
     - `/Continue` & `/Pause`：無縫暫停凍結與現場斷點接續恢復
     - `/Roadmap`：長期策略路線圖智能推薦與一鍵轉化
  3. **6 大計畫分支拓撲與生命週期 (Plan Taxonomy)**：
     - Level 0 (Fast Track)、Level 1 (Full Track SOP 0~7)、Level 2 (Umbrella 雙軌拓撲)、Revision (修訂短循環)、Research (調研三步法)、Roadmap (長期策略資產)。
  4. **Agent 核心行為準則與防呆紀律 (Core Axioms & Guardrails)**：
     - 三大原則：零臆測、剛性追溯、分級管控。
     - 執行紀律：嚴禁連發、Checkpoint 強制等待、「問答 $\neq$ 推進」防呆、除錯範疇保護、確定性讀檔阻斷、CLI Default-Deny 守門。
  5. **純用戶 CLI 指令集速查**：
     - 計畫管理：`plan status`, `plan verify <name>`, `plan search <query>`, `plan archive <name>`, `plan --init-default`
     - 路線圖管理：`roadmap`, `roadmap --list`
     - 工作流編譯與發布：`compile` (alias `build`), `release`, `release-target`, `tokens`, `list`
  6. **實用 Cookbook**：新專案一鍵初始化工作流、日常計畫推進與查核、完成計畫封存。
- **影響範圍**：
  - 新增：[`source/agents-workflow/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/README.md)（隨模組發布打包分發給所有下游用戶）
- **Fast Track 4 維度確認**：
  - [x] 修改行數預估 $\le 100$ 行 (文檔型任務)
  - [x] Public API 契約 0 變更
  - [x] 架構自包含、零外部 `docs/` 依賴
  - [x] 既有測試/CLI 可 100% 驗證指令正確性

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：撰寫並交付 100% 自包含的 [`source/agents-workflow/README.md`](file:///H:/UseFolder/CodeRepo/ys_codebase/ys_codebase/source/agents-workflow/README.md)。
- **測試案例**：
  - `FT-01`：驗證文檔內所有示範之 `python yscb.py agents-workflow` CLI 指令均能在真實環境中無誤解析與執行。
  - `FT-02`：以 `dev test agents-workflow` 驗證模組測試 100% 通過且無回歸。
  - `FT-03`：驗證 `source/agents-workflow/README.md` 完全自包含，無指向外部 `docs/` 的斷鏈。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  - 已於 `source/agents-workflow/README.md` 產出完整自包含說明手冊，涵蓋四層架構全景圖、10 大 Slash Commands 導覽表、6 大計畫分支拓撲決策圖、Agent 核心三大公理與 6 大防呆條款、全量 CLI 指令速查與 2 大典型情境 Cookbook。
- **實機測試日誌**：
  - `dev test agents-workflow`：43/43 測試全數通過（3 契約測試 + 40 自訂單元測試，耗時 9.69s）。
  - `dev check agents-workflow`：合規靜態檢查 100% Passed。
  - CLI 指令驗證（`plan status`, `tokens`, `list` 等）：解析執行 100% 正常。

---

## 3. 結案與交付確認 (FT-3 Closure & Walkthrough)

- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_08_29_2035_user_guidance_and_module_readme_enhancement/sub_03_agents_workflow_readme` 驗證 100% Passed。
- **結案狀態**：`Completed`
