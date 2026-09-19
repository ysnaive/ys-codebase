# Fast Track 敏捷開發計畫 (Fast Track Plan)

> 功能名稱：server_daemon_agent_directive_refinement  
> 建立日期：2026-09-19  
> 所屬主計畫：無 (獨立敏捷修復)  
> 狀態：Completed  

> 計畫類型：Level 0 Fast Track  
> 模板版本：v1.2  

---

## 1. 敏捷需求與實作計畫 (FT-1 Specification & Plan)

### 1.1 核心需求與邊界
- **需求背景與歸因**：
  1. 下游專案反饋 AI Agent 常忽略 Server 自動喚醒失敗時的 CLI 提示。經歸因分析，原提示存在「語意順序倒置（降級成因置頂）」、「語意消毒（提及降級冷派發 ~86ms 使 Agent 誤判無風險）」與「缺少負向阻斷約束（未明確禁止在未啟動前繼續執行指令）」等問題，且包含 Antigravity 特化參數 `run_command + IsDaemon: true` 造成跨 Agent 工具洩漏。
  2. 開發者反饋 Agent 在推進主目標時，遇非主要衍生問題常採用死代碼、低維護性、靜默吞錯等敷衍方案（Shallow Fixes）以求表面通過測試。需於 Agents Standards 補充剛性規範約束。
- **改進目標**：
  1. 將 Server 自動喚醒提示結構重構為醒目之 `[BLOCKER]` 前置阻斷約束，行動方針絕對置頂。
  2. 抽象化工具描述為跨平台通用的「背景/常駐模式 (Background/Daemon task)」，消除特定 IDE 工具相依。
  3. 修正處置方針：引導 Agent 向開發者回報阻斷狀態與請示方案（外部啟動 / 評估關閉 auto_spawn / (不推薦) 冷派發繼續），嚴禁 Agent 自行擅改專案共享組態。
  4. 移除安撫性冷派發毫秒數據，強調沙盒限制與避免持續以此模式作業。
  5. 於 `AgentsStandards.md` 補充核心原則第 4 條：「嚴禁淺層敷衍與架構債逃逸 (Zero Shallow Patches & Architecture Integrity Axiom)」，定義反模式清單與次要衍生問題處置鐵律，並透過發布同步更新專案 `AGENTS.md`。
- **4 大剛性守門檢核**：
  - [x] 代碼修改行數 $\le 100$ 行（實際修改 $\sim 45$ 行）。
  - [x] Public API 簽名契約 0 變更。
  - [x] 零跨模組新依賴引入。
  - [x] 既有單元測試套件 100% 覆蓋守門。
- **影響範圍**：
  - `source/core/core/commands/dispatcher.py` (`_maybe_auto_spawn_server`)
  - `source/core/tests/test_core_commands.py` (`test_ft12`, `test_ft13`)
  - `source/agents-workflow/assets/standards/AgentsStandards.md`
  - `AGENTS.md` (透過 release 同步)
  - `source/agents-workflow/tests/test_initializer.py` (修復測試環境 config 還原)
  - `source/agents-workflow/tests/test_publisher.py` (修復 test_ft_14 docs 隔離)

### 1.2 實作任務與測試規劃
- [x] **TASK-01**：於 `dispatcher.py` 更新 `_maybe_auto_spawn_server` 提示詞模板為定稿之 `[BLOCKER]` 阻斷語句結構。
- [x] **TASK-02**：於 `test_core_commands.py` 更新 `test_ft12` 與 `test_ft13` 斷言字串並確保通過。
- [x] **TASK-03**：於 `AgentsStandards.md` 補充第 4 條核心原則「嚴禁淺層敷衍與架構債逃逸」。
- [x] **TASK-04**：執行 `dev test core` (192/192 Passed) 與 `dev test agents-workflow` (79/79 Passed) 回歸測試，執行 `dev check`。
- [x] **TASK-05**：安裝並發布更新（`install core@build`、`install agents-workflow@build`），實機驗證 `plan status` 渲染與 `AGENTS.md` 注入。
- **測試案例**：
  - `FT-01`：`test_ft12_maybe_auto_spawn_server_adaptive_degrade`（驗證包含 `[BLOCKER]`、通用常駐啟動指令與三項請示方案通過）。
  - `FT-02`：`test_ft13_maybe_auto_spawn_server_warning_debounce`（驗證單進程去重防洗頻通過）。
  - `FT-03`：`test_standards_compilation` 與全套 `agents-workflow` (79/79 Passed)。

---

## 2. 實作與驗證成果 (FT-2 Execution & Test Log)

- **實作結果**：
  1. `dispatcher.py`: Server auto_spawn 提示重構為 `[BLOCKER]`，置頂負向阻斷條款，移除毫秒干擾，支援通用常駐描述與三項請示方案（A/B/C，C 標註不推薦）。
  2. `AgentsStandards.md`: 補充第 4 條核心原則「嚴禁淺層敷衍與架構債逃逸」，定義 4 大反模式紅線與次要衍生問題處置鐵律；發布後自動注入至專案 `AGENTS.md`。
  3. `test_initializer.py` & `test_publisher.py`: 深度歸因修復沙盒測試中 `config.project.json` 未正確還原引發的 Windows 跨槽 `ValueError`，使全套測試 100% 綠燈通過。
- **實機測試日誌**：
  - `dev test core`: 192 Total, 192 Passed, 0 Failed (41.98s)
  - `dev test agents-workflow`: 79 Total, 79 Passed, 0 Failed (24.13s)
  - `dev check core`: PASSED (0 warnings, 0 errors)
  - `dev check agents-workflow`: PASSED (0 warnings, 0 errors)
  - 實機驗證 `python yscb.py agents-workflow plan status`: 渲染標準 `[BLOCKER]` 橫幅無誤。

---

## 3. SOP Review 審查與結案交付 (Review & FT-3 Closure)

- [x] **SOP Review 品質矩陣**：三層文檔對齊、測試 100% 通過。
- [x] **日誌與發布交付**：追加 `project://CHANGELOG.md` 發布摘要。
- [x] **結構與註解檢核**：實機執行 `python yscb.py agents-workflow plan verify 2026_09_19_1433_server_daemon_agent_directive_refinement` 驗證 100% Passed。
- **結案狀態**：`Completed`
