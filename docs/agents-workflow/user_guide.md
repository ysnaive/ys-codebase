---
target: "Agents-Workflow/UserGuide"
doc_type: "topic"
status: "active"
source_paths:
  - "yscb://source/agents-workflow/agents_workflow/commands.py"
  - "yscb://source/agents-workflow/agents_workflow/plans/verifier.py"
  - "yscb://source/agents-workflow/agents_workflow/plans/archiver.py"
  - "yscb://source/agents-workflow/agents_workflow/plans/status.py"
  - "yscb://source/agents-workflow/agents_workflow/plans/searcher.py"
related_docs:
  - "./README.md"
  - "./FACTORY_PIPELINE.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-10-17"
---

# Agents Workflow 使用者與操作指南 (User Guide)

本文件提供 `agents-workflow` 模組的完整操作指引，特別針對 **Dev Plans 開發計畫工具鏈**（`plan archive`, `plan status`, `plan search`, `plan verify`）與純 Skill 發布治理進行深度說明。

---

## 1. Dev Plans 工具鏈 (Plans Management Toolchain)

YS-Codebase 將所有開發計畫管理功能收斂為原生 CLI 子指令，零依賴硬編碼路徑，全面透過 `core.uri` 解析語意空間（`workflow.plans://` 與 `workflow.archived://`）。

### 1.1 計畫狀態矩陣掃描 (`plan status`)

掃描當前專案活躍進行中的開發計畫（`workflow.plans://`），即時解析各計畫之 Track 類型（`Umbrella`, `Fast Track`, `Full Track`, `Revision`, `Phase 0`）與當前 Phase 狀態，並以樹狀縮排展示子計畫階層。

- **正交修訂計畫 (`revision_log.md`) 掃描規則**：
  - **附隨型修訂**：當 `revision_log.md` 附隨於既有計畫（`Full Track`、`Fast Track`、`Umbrella` 或 `sub_XX` 子計畫）時，**不影響**原主計畫或子計畫的 Track 顯示與狀態判定。
  - **獨立型修訂**：當計畫目錄不含 `umbrella_overview.md`、`fast_track_plan.md` 與 `P01+`，而由 `revision_log.md` 單獨組成（或搭配前置 `P00` / `RXX`）時，`Track 模式` 顯示為 `Revision`。

```bash
# 掃描並展示進行中開發計畫狀態矩陣
python yscb.py agents-workflow plan status
```

> [!NOTE]
> 依據設計規範，`plan status` 專注於活躍進行中計畫，**不掃描歷史封存目錄**。

#### 輸出範例
```text
==========================================================================================
計畫名稱 / 子計畫                                           | Track 模式        | 當前狀態             | 位置
==========================================================================================
2026_10_14_1224_deep_audit_and_ecosystem_refinement   | Umbrella        | Completed        | plans/
  └─ sub_01_host_and_core_foundation_remediation      | Full Track      | Completed        | plans/
  └─ sub_06_downstream_cli_ux_and_server_feedback     | Full Track      | Completed        | plans/
2026_10_17_0900_ui_spacing_and_docs_polish            | Revision        | In Progress      | plans/
==========================================================================================
```

---

### 1.2 計畫安全歸檔 (`plan archive`)

將已結案的計畫安全搬移至歷史年/月封存目錄（`workflow.archived://{YYYY}/{MM}/{plan_name}/`）。

```bash
# 標準歸檔（觸發 4 重守門檢查）
python yscb.py agents-workflow plan archive 2026_08_20_1200_demo_feature

# 強制歸檔（略過 Completed 標記與 CHANGELOG 記載檢查）
python yscb.py agents-workflow plan archive 2026_08_20_1200_demo_feature --force
```

#### 4 重守門安全防護
1. **完成狀態與附隨修訂守門**：檢查主計畫完成產物（`P07_walkthrough.md`、`fast_track_plan.md`、`umbrella_overview.md` 或獨立修訂計畫之 `revision_log.md`）是否標記 `Completed`；同時額外巡檢計畫根目錄與所有 `sub_*` 子計畫目錄，若存在任何 `revision_log.md` 未標記為 `Completed`，將拋出 `PlanIncompleteError` 強制阻斷歸檔（除非加上 `--force`）。
2. **CHANGELOG 登載守門**：核對專案根目錄 `CHANGELOG.md` 是否已記載該計畫發布紀錄。
3. **現場快照清理**：自動偵測並物理刪除殘留的暫時性交接快照 `handoff.md`。
4. **目的地衝突防護**：若 `workflow.archived://{YYYY}/{MM}/{plan_name}/` 已存在同名目錄，強制阻斷防止覆蓋。

---

### 1.3 歷史與決策檢索 (`plan search`)

跨活躍進行中與歷史歸檔計畫檢索決策記錄 (DR) 或全文關鍵字。

```bash
# 1. 檢索架構決策記錄 (DR模式，正則結構化擷取並自動去重)
python yscb.py agents-workflow plan search --dr
python yscb.py agents-workflow plan search "URI" --dr
python yscb.py agents-workflow plan search --dr --year=2026 --month=10 --limit=15

# 2. 跨計畫全文程式碼檢索（展示匹配行號與前後上下文）
python yscb.py agents-workflow plan search "PlanArchiver"
python yscb.py agents-workflow plan search "VFS" --limit=10
```

#### 輸出範例 (DR 模式)
```text
==========================================================================================
Plan 名稱 / 來源檔案                           | DR ID / 標題             | 結論 / 摘要
==========================================================================================
2026_08_25_2200_agents_workflow_migr...   | [P01:DR-01] 舊版 4 大腳...  | 完整收斂至 agents-workflow.plans 子套件...
2026_08_25_2200_agents_workflow_migr...   | [P02:DR-01] 階梯式封裝...   | 建立專屬 plans 子套件，定義自定義例外...
==========================================================================================
```

---

### 1.4 計畫規範與合規性稽核 (`plan verify`)

由 `PlanVerifier` 全面稽核活躍計畫之 Markdown 文件是否符合開發標準規範，及早攔截模板佔位符殘留、模型標頭缺失、未完成待辦項與章節標題漂移。

```bash
# 稽核所有活躍進行中計畫（預設行為，與 --all 等價）
python yscb.py agents-workflow plan verify

# 稽核指定活躍計畫
python yscb.py agents-workflow plan verify 2026_10_14_1224_deep_audit_and_ecosystem_refinement

# 顯式指定檢核所有活躍計畫（僅掃描 workflow.plans:// 活躍計畫，不掃描歷史封存目錄）
python yscb.py agents-workflow plan verify --all
```

#### `PlanVerifier` 核心檢核規則
- **僅掃描活躍計畫邊界**：`verify_all_plans()`（含 `--all`）專注於檢核 `workflow.plans://` 下之活躍開發計畫（自動排除 `archived/` 與 `roadmap/`），不回溯掃描歷史已歸檔封存計畫。
- **Header 元數據與 `> 模型：` 標頭強制檢核**：驗證 Markdown 開頭 Blockquote 是否齊備 `功能名稱`（或 `計畫名稱`）、`建立日期`、`狀態`（或 `計畫狀態`）以及 **`> 模型：`**（`has_model` 剛性檢查；填入平台當輪宣告之名稱，無法確認填 `Unknown`）。驗證器僅檢查欄位存在，**不驗證名稱真偽**，且不得據此反推模型。
- **未填寫佔位符與指引攔截**：偵測檔案內是否殘留 `<!-- AGENT_GUIDANCE -->` 模板指引註解，或未替換之模板佔位符（如 `[平台宣告之模型名稱；無法確認填 Unknown]`、`[模型名稱]`、`[Model Name]`、`[YYYY-MM-DD]`、`[專案/功能名稱]`、`[修訂主題簡述]`、`[UI/UX/DX | Parameter | Docs]` 等）。
- **`Completed` / `Concluded` 狀態未勾選 `- [ ]` 阻斷**：當文件標頭狀態標記為 `Completed` 或 `Concluded` 時，若內文仍存在任何未勾選之待辦 Checkbox（`- [ ]`），直接判定為 `FAIL` 阻斷通過。
- **動態章節標題對齊、修訂條目檢核與子計畫遞迴覆蓋**：動態比對 `.agents/.yscb/templates/` 標準模板的一級/二級章節標題（針對 `revision_log.md` 自動豁免動態條目子標題 `### [REV-XX]` 並強制檢核至少包含一筆 `[REV-XX]` 修訂紀錄），且自動深入 `sub_*` 子計畫目錄遞迴執行全套稽核。

---

### 1.5 長期技術路線圖管理 (`roadmap`)

掃描並條列 `workflow.roadmap://`（預設為 `plans/roadmap/`）儲備庫中的長期技術藍圖與策略資產。

```bash
# 條列所有 Roadmap 主題摘要對照表（支援 --status 過濾）
python yscb.py agents-workflow roadmap [--list] [--status=Candidate]

# 檢視指定主題之詳細背景與路徑
python yscb.py agents-workflow roadmap release_binary_storage_optimization
```

---

## 2. 技能資產發布與組態治理

### 2.1 專案組態開關 (`config.project.json`)
位於 `config://agents-workflow/config.project.json`：
```json
{
  "paths": {
    "plans": "!undefined",
    "archived": "!undefined",
    "docs": "!undefined",
    "roadmap": "!undefined"
  },
  "release_targets": [],
  "enable_project_changelog": true
}
```
- **`release_targets`**：預設為空清單 `[]`。指定欲啟用的 Target（例 `["antigravity"]`），發布時將資產投影輸出至對應目錄與各 Target 宣告之 `agents_md` 規範檔案路徑。
- **`enable_project_changelog`**：控制是否啟用全專案 `project://CHANGELOG.md` 結案登載與歸檔守門要求。

### 2.2 一鍵工作流初始化 (`init --default`)
```bash
# 初始化 workflow.plans://, workflow.archived://, workflow.docs://, workflow.roadmap:// 目錄結構與組態
python yscb.py agents-workflow init --default -y
```

### 2.3 原子發布交易 (`release`)
```bash
# 執行 4 步原子交易發布至各 Target 投影目錄並軟合併規範檔案
python yscb.py agents-workflow release [target_name] [--force]
```
- **特性**：
  - 若 `release_targets` 為空 `[]`，安全略過投影目錄寫入（`Published files: 0`）。
  - 各啟用 Target 依其 `agents_md` 宣告路徑（如 `project://AGENTS.md` 或 `project://CLAUDE.md`）自動提取 `AgentsStandards.md` 執行軟合併更新，保留專案特化規則。

### 2.4 多平台 Release Targets 矩陣與管理 (`release-target`)

`agents-workflow` 原生支援多種 AI 程式碼助理與 IDE 之純 Skill 發布投影拓撲：

| Target 名稱 | 適用平台 / IDE | Skills 投影目錄 | Templates / Standards | 規則檔支援 |
| :--- | :--- | :--- | :--- | :--- |
| **`antigravity`** | Google Antigravity IDE | `.agents/skills/{export.name}/` | `.agents/.yscb/templates/`, `.agents/.yscb/standards/` | `AGENTS.md` (軟合併) |
| **`claude`** | Anthropic Claude Code | `.claude/skills/{export.name}/` | `.claude/.yscb/templates/`, `.claude/.yscb/standards/` | `CLAUDE.md` (軟合併) |
| **`codex`** | OpenAI Codex (CLI / VS Code) | `.agents/skills/{export.name}/` | `.agents/.yscb/templates/`, `.agents/.yscb/standards/` | `AGENTS.md` (軟合併) |

#### CLI Target 管理指令
```bash
# 檢視當前已宣告與已啟用的 Targets 清單
python yscb.py agents-workflow release-target --list

# 啟用指定 Target 並自動執行發布物化 (加 --proj 寫入團隊共享組態)
python yscb.py agents-workflow release-target --add claude [--proj]
python yscb.py agents-workflow release-target --add codex [--proj]

# 停用指定 Target 並自動清理歷史檔案
python yscb.py agents-workflow release-target --remove claude [--proj]
```

---

## 3. CLI 指令防呆手冊與 Default-Deny 守門機制 (`yscb-cli-guide`)

### 3.1 宣告式 CLI 防呆技能 (`yscb-cli-guide/SKILL.md`)
由 `agents-workflow` 導出並物化至 `.agents/skills/yscb-cli-guide/SKILL.md`。透過 Core 模組動態 Token `AGENTS_CLI_GUIDE`，自動收集所有已安裝模組在 `contributes.core.commands`（經 `__modules__` 雙層分桶隔離）中宣告的權限等級、推薦情境 (`case_pros`) 與禁止情境 (`case_cons`)。

### 3.2 Agent 調用守門鐵律
1. **查表比對 (Look Up & Match)**：Agent 執行任何 `python yscb.py` 命令前必須比對 `yscb-cli-guide` 技能手冊。
2. **Default-Deny 閉環 (Default-Deny Gate)**：若欲執行之命令未列於表、無對應推薦欄位、或命中 `[GATED]` / `[!] 絕對禁止/不適用情境`，Agent 絕對禁止擅自執行，必須向開發者呈遞調用意圖與完整命令列，獲明確授權後方可執行。

---

## 4. 模板佔位符語意體系 (Placeholder System)

編譯器在執行資產 Stage 1 與 Stage 2 編譯時，支援結構化語意佔位符：

| 佔位符 | 語意分類 | 解析基準點 | 適用情境與範例 |
| :--- | :--- | :--- | :--- |
| **`` `__@{token}__` ``** | **文件內容佔位符** | Stage 1 內容狀態機 | 常數注入、模板片段嵌入、`code.func://` 動態計算產出（例：`` `__@{AGENTS_CLI_GUIDE}__` ``）。 |
| **`` `__#{uri}__` ``** | **自身相對路徑佔位符** | 當前 Markdown 文件所在目錄 (`cur_doc_dir`) | Markdown 文本內部超連結導航（例：`[標準](`__#{module://.../SKILL.md}__`)` $\to$ `[標準](../development-sop/SKILL.md)`）。 |
| **`` `__${uri}__` ``** | **專案根目錄相對路徑佔位符** | 專案根目錄 (`project://`) | 終端機 Shell 執行指令與專案相對路徑參照（例：`` `python __${yscb.host://yscb.py}__ run` `` $\to$ `` `python yscb.py run` ``）。 |
| **`` `__$(起始錨點){uri}__` ``** | **動態起點相對路徑佔位符** | 指定之起始錨點目錄 (`anchor`) | 跨目錄或特定基準點相對路徑計算（例：`` `__$(project://docs){workflow.docs://core/README.md}__` `` $\to$ `core/README.md`）。 |

### 4.1 反引號包裹與穿插展開
- **強制包裹**：佔位符必須由反引號（代碼塊 `` `...` ``）包裹方可被解析。
- **穿插替換**：支援在同一個代碼塊中穿插其他文字（例如 `` `python __${yscb.host://yscb.py}__ agents-workflow plan status` ``），展開時僅替換佔位符字串，保留前後文字與外層反引號。
- **未包裹警示**：若文本中出現未被反引號包裹的裸佔位符，編譯器不予展開並輸出 `[compiler:warning]` 警示提示。

---

## 5. 自動連續推進技能 (`auto` Skill)

### 5.1 核心定位與觸發時機
`/Auto`（對應 `auto` 技能）為可在 **Phase 01 ~ Phase 05** 之間觸發的連續推進模式。當開發者確認需求（Phase 0 完成）後，下達 `/Auto` 授權 Agent 在無技術歧義與無爭議的前提下，跳過中間各 Phase 的強制 Checkpoint 等待，自動連續產出各階段規範與代碼實作，直達 Phase 6 手動/UX 驗證前。

### 5.2 適用範圍與分流
- **Full Track (Level 1)**：進行中計畫。
- **Umbrella (Level 2)**：主計畫下處於進行中狀態之 Full Track 子計畫 (`sub_XX`)。
- **排除 Fast Track (Level 0)**：Fast Track 無多階段等待需求，不適用 `/Auto`。

### 5.3 三大熔斷防線 (Circuit Breakers)
1. **零臆測熔斷 (Zero Speculation Gate)**：遇到任何需求不明或技術未知，立即停手提問。
2. **偏差熔斷 (Deviation Gate)**：遇到 Major/Critical 架構或 API 偏差，立即停止並轉入 `/Discuss`。
3. **P06 手動/UX 驗證絕對阻斷 (Mandatory UX Gate)**：CLI 自動化測試通過後，強制停步等待開發者人工/UX 驗收，絕對禁止自動結案。
