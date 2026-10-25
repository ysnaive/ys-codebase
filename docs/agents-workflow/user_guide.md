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
  - "yscb://source/agents-workflow/agents_workflow/roadmap.py"
related_docs:
  - "./README.md"
  - "./FACTORY_PIPELINE.md"
  - "./DESIGN_NOTES.md"
last_updated: "2026-10-25"
---

# Agents Workflow 使用者與操作指南 (User Guide)

本文件提供 `agents-workflow` 模組的完整操作指引，特別針對 **Dev Plans 開發計畫工具鏈**（`plan archive`, `plan status`, `plan search`, `plan verify`）與純 Skill 發布治理進行深度說明。

---

## 1. Dev Plans 工具鏈 (Plans Management Toolchain)

YS-Codebase 將所有開發計畫管理功能收斂為原生 CLI 子指令，零依賴硬編碼路徑，全面透過 `core.uri` 解析語意空間（`workflow.plans://` 與 `workflow.archived://`）。

### 1.1 計畫狀態矩陣掃描 (`plan status`)

掃描當前專案活躍進行中的開發計畫（`workflow.plans://`），即時解析各計畫之 Track 類型（`Umbrella`, `Fast Track`, `Full Track`, `Revision`, `Phase 0`, `Seeded`）與當前 Phase 狀態，並以樹狀縮排展示子計畫階層。

- **起源種子狀態 (`Seeded`) 識別規則**：
  - 當計畫目錄或 `sub_XX` 子計畫目錄剛由 `roadmap promote` 或 `todo promote` 建立，僅含起源種子檔（`roadmap.md` 或 `todo.md`）與 `changelog.md`、尚未補齊首份正式規格檔（`P00_discuss.md`、`fast_track_plan.md`、`revision_log.md` 或 `umbrella_overview.md`）時，`Track 模式` 顯示為 `Seeded`，`當前狀態` 顯示為 `Seeded (Pending Plan)`，`PlanStatusResolver` 會明確引導於該目錄原地補齊規格檔。
  - 一旦補齊首份正式規格檔，起源種子檔（`roadmap.md` / `todo.md`）即轉為唯讀背景上下文，不再影響後續 Phase 狀態推導。
- **正交修訂計畫 (`revision_log.md`) 掃描規則**：
  - **附隨型修訂**：當 `revision_log.md` 附隨於既有計畫（`Full Track`、`Fast Track`、`Umbrella` 或 `sub_XX` 子計畫）時，**不影響**原主計畫或子計畫的 Track 顯示與狀態判定。
  - **獨立型修訂**：當計畫目錄不含 `umbrella_overview.md`、`fast_track_plan.md` 與 `P01+`，而由 `revision_log.md` 單獨組成（或搭配前置 `P00` / `RXX`）時，`Track 模式` 顯示為 `Revision`。

```bash
# 1. 掃描並展示進行中開發計畫狀態矩陣 (100% 純唯讀)
python yscb.py agents-workflow plan status

# 2. 確定性狀態領航與 handoff.md 原子閱後即焚 (Consume & Delete)
python yscb.py agents-workflow plan status --resume [--plan <plan_name_or_subpath>]
```

- **確定性狀態領航與 `--resume` 原子閱後即焚**：
  - `PlanStatusResolver.resolve_next_action` 自動深入 `Umbrella` 第一個未結案之活躍 `sub_XX` 子目錄，依據檔案與標頭狀態輸出 `Plan Mode`、`Current Breakpoint`、`Next Phase`、`Required Reference`（下一步必讀之 SOP 階段參考手冊路徑）與行動提示。
  - 當傳入 `--resume` 且目標目錄存在 `handoff.md` 時，終端完整輸出快照內容後立即由 Python 呼叫 `os.unlink()` 物理刪除該檔案；未傳入 `--resume` 時維持 100% 純唯讀掃描。
  - 若同時存在多個進行中計畫且未指定 `--plan`，為遵守零臆測原則，系統拒絕盲目挑選或刪除任何 `handoff.md`，並提示顯式傳入 `--plan`。

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

# 稽核指定活躍計畫或子計畫
python yscb.py agents-workflow plan verify 2026_10_14_1224_deep_audit_and_ecosystem_refinement

# 單階段左移檢核、伴隨檔自癒 (P06 Draft / changelog.md) 與免讀盲寫追加日誌
python yscb.py agents-workflow plan verify [plan_name_or_subpath] --phase P02 --log "完成 P02 架構設計與 P06 Draft 初始化" --model "Gemini 4 Argon (Low)"
```

#### `PlanVerifier` 核心檢核與自癒規則
- **僅掃描活躍計畫邊界**：`verify_all_plans()`（含 `--all`）專注於檢核 `workflow.plans://` 下之活躍開發計畫（自動排除 `archived/` 與 `roadmap/`），不回溯掃描歷史已歸檔封存計畫。
- **四步執行管線與 `--log` 免讀盲寫追加 (`4-Step Self-Healing & Zero-Read Log Pipeline`)**：
  1. **Step 1 (主體檔檢核)**：先針對 `--phase <P00..P07|current|all>` 目標階段主體檔執行合規檢核。
  2. **Step 2 (伴隨檔自癒)**：若 Step 1 無 `FAIL` 且提供 `--log`，自動從模板初始化缺失之 `changelog.md` 與 `P02` 伴隨之 `P06_test_plan.md (Draft)`（伴隨檔模型優先取 `--model`，次取同階段主體檔標頭，否則填 `Unknown`，嚴禁跨階段回溯舊檔）。
  3. **Step 3 (雙檔協同與 `P01<->P06` 追溯差集比對)**：檢核 `P02` 時確認 `P06_test_plan.md` 存在；檢核 `P04+` 時確認 `P06_test_plan.md` 標頭狀態已達 `Confirmed` 以上，並自動提取 `P01` 之 `FR-\d+`/`EC-\d+`/`NFR-\d+`（預先剝除代碼塊、HTML 註解與 `~~...~~` 刪除線）與 `P06` 比對集合差集，精確攔截孤兒需求 ID。
  4. **Step 4 (免讀盲寫與冪等防重入)**：僅當檢核 100% `PASS`（0 `FAIL`）時，自動以系統當前時間 `YYYY-MM-DD HH:MM` 於 `changelog.md` 表格頂部插入紀錄列，並比對首筆資料列之 `(類型, 摘要)` 防止重複寫入。
- **自癒型可操作修復指引 (`Actionable Fix Hint`)**：所有 `FAIL` / `WARN` 診斷訊息均附帶 `[Fix Hint: ...]` 具體修復步驟。
- **Header 元數據與 `> 模型：` 標頭強制檢核**：驗證 Markdown 開頭 Blockquote 是否齊備 `功能名稱`（或 `計畫名稱`）、`建立日期`、`狀態`（或 `計畫狀態`）以及 **`> 模型：`**（`has_model` 剛性檢查；填入平台當輪宣告之名稱，無法確認填 `Unknown`）。驗證器僅檢查欄位存在，**不驗證名稱真偽**，且不得據此反推模型。
- **未填寫佔位符與指引攔截**：偵測檔案內是否殘留 `<!-- AGENT_GUIDANCE -->` 模板指引註解，或未替換之模板佔位符（如 `[平台宣告之模型名稱；無法確認填 Unknown]`、`[模型名稱]`、`[Model Name]`、`[YYYY-MM-DD]`、`[專案/功能名稱]`、`[修訂主題簡述]`、`[UI/UX/DX | Parameter | Docs]` 等）。
- **`Completed` / `Concluded` 狀態未勾選 `- [ ]` 阻斷**：當文件標頭狀態標記為 `Completed` 或 `Concluded` 時，若內文仍存在任何未勾選之待辦 Checkbox（`- [ ]`），直接判定為 `FAIL` 阻斷通過。
- **動態章節標題對齊、修訂條目檢核與子計畫遞迴覆蓋**：動態比對 `.agents/.yscb/templates/` 標準模板的一級/二級章節標題（針對 `revision_log.md` 自動豁免動態條目子標題 `### [REV-XX]` 並強制檢核至少包含一筆 `[REV-XX]` 修訂紀錄），且自動深入 `sub_*` 子計畫目錄遞迴執行全套稽核。

---

### 1.5 雙層技術儲備與待辦管理 (`roadmap` & `todo`)

YS-Codebase 採用「宏觀路線圖（`workflow.roadmap://{topic}.md`）+ 微觀待辦帳本（`workflow.roadmap://TODO.md`）」雙層分流治理與 **立項即消耗 (`Consume-on-Promote`)** 生命週期：

1. **宏觀策略路線圖 (`roadmap`)**：適用於跨模組架構演進或需多階段推進之長期藍圖。純儲備階段之有效狀態收斂為 `[Backlog | Proposed | Ready | Deferred]`，並記載 `> 目標範疇：` 與 `> 前置解鎖條件：`。當開發者拍板立項時，執行 `roadmap promote` 將 `plans/roadmap/{topic}.md` **物理移轉 (`shutil.move`)** 至新計畫目錄（或既有 `--plan` 目錄）並重命名為 `roadmap.md`，同時自動伴隨初始化 `changelog.md`。
2. **微觀待辦帳本 (`todo`)**：適用於單一檔案微調、小範圍重構點子或次要技術債速記，統一集中於單一帳本 `workflow.roadmap://TODO.md`（由標頭 `> 最後分配編號：N` 維護單調遞增 `TODO-XXX` 編號，並由 `RoadmapManager` 自動排除不混入路線圖列表）。立項時透過 `todo promote` 支援單筆或多筆打包提取（Pop），將選中列自 `TODO.md` 原子移除並於目標計畫目錄生成 `todo.md` 起源種子檔與 `changelog.md`。

```bash
# 1. 宏觀路線圖列表查詢（支援 --status 過濾，自動排除 TODO.md）與單一主題檢視
python yscb.py agents-workflow roadmap [list] [--status <Backlog|Proposed|Ready|Deferred>]
python yscb.py agents-workflow roadmap <topic>

# 2. 宏觀路線圖消耗立項 (Consume-on-Promote：物理移轉為計畫內 roadmap.md + 初始化 changelog.md)
python yscb.py agents-workflow roadmap promote <topic> [--plan <dir>] [--model "<ModelName>"]

# 3. 微觀待辦單行免讀盲寫追加 (自動分配單調遞增 TODO-XX 編號)
python yscb.py agents-workflow todo add "<標題>" [--scope <範疇>] [--note "<備忘>"] [--model "<ModelName>"]

# 4. 微觀待辦清單檢視與過濾
python yscb.py agents-workflow todo list [--scope <關鍵字>]

# 5. 微觀待辦單筆或多筆打包提取立項 (Pop & Seed：自 TODO.md 移除並生成計畫內 todo.md + changelog.md)
python yscb.py agents-workflow todo promote <TODO-ID> [TODO-ID...] --slug <plan_slug> [--plan <dir>] [--model "<ModelName>"]
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

## 3. CLI 執行防呆慣例與 `-h` 按需自省機制 (`yscb-cli-guide`)

### 3.1 輕量防呆與漸進式自省 (`yscb-cli-guide/SKILL.md`)
由 `agents-workflow` 導出並物化至目標平台 `yscb-cli-guide/SKILL.md`（收斂至 $\le 65$ 行、$< 1,100$ Tokens）。為消除全系統動態指令大表隨模組擴充帶來的無界 Token 膨脹與查表延遲，系統徹底拔除 `core.providers:get_agents_cli_guide` 靜態大表生成，改採以下雙軌調用與 `-h` 按需自省架構：

### 3.2 雙軌調用與 Default-Deny 守門鐵律
1. **軌跡 A — 技能內建指令免查直跑 (`Skill-Vetted Fast Pass`)**：凡於各工作流與工具技能（如 `development-sop`、`knowledge-db-search`、`yscb-module-dev`、`todo`、`roadmap` 等）步驟中已明文列出完整語法的標準指令，均已預審為 `[SAFE]`（或由該技能內建確認節點守門），Agent 可直接執行，無須額外查表或執行 `-h`。
2. **軌跡 B — 非常規指令／未知參數強制 `-h` 自省 (`Just-in-Time -h Inspection`)**：當準備調用未在當前技能明文列出之指令、嘗試非標準選項旗標或確認權限時，強制先執行 `python yscb.py <module> [command] [subcommand] -h`，由 `HelpRenderer` 即時渲染 `Security : [SAFE]/[CONDITIONAL]/[GATED]`、`ARGUMENTS`、`OPTIONS`、`RECOMMENDED USAGE (Pros)` 與 `RESTRICTIONS & GATES (Cons)`。
3. **`[GATED]` 紅線家族 Default-Deny 閉環**：凡命中環境異動（`install` [除開發期 `@build` 外]、`remove`、`update`、`rollback`、`init`）、打包發布與版本晉升（`dev release`、`/bump-revision`）、封存與快取清理（`plan archive`、`clean`）或 `op-*` 運維指令家族，未獲開發者於當前輪次顯式授權前絕對禁止主動執行。

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

## 5. 自動連續推進技能 (`auto` Skill — Lean Context Fast-Path)

### 5.1 核心定位與觸發時機
`/Auto`（對應 `auto` 技能）為可在 **Phase 00 (`Confirmed`) 或 Phase 01 ~ Phase 05** 之間觸發的連續推進模式。當開發者確認需求或前置階段規格後，下達 `/Auto` 授權 Agent 在無技術歧義與無爭議的前提下，跳過中間各 Phase 的強制 Checkpoint 等待，以精實模式自動連續產出各階段規範與代碼實作，直達 Phase 6 手動/UX 驗證前。

### 5.2 `_auto.md` 專屬後綴命名規範與 Context 精實化三大機制
1. **`PXX_YYYY_auto.md` 動態溯源命名鐵律 (`_auto` Suffix Provenance Rule)**：
   - 凡於 `/auto` 過程中由 Agent 一次自動寫入之階段規格與任務檔（涵蓋自當前啟動階段至 `Phase 05`），檔名強制附加 `_auto` 後綴（即 `P01_requirements_spec_auto.md`、`P02_architecture_plan_auto.md`、`P03_api_spec_auto.md`、`P04_implementation_plan_auto.md`、`P05_task_auto.md`）：
     - 若於 `P00` 定案後即觸發 `/auto`，則 `P01`~`P05` 全數帶 `_auto.md` 後綴。
     - 若人工討論定案至 `P02` 後才觸發 `/auto`，則 `P00`~`P02` 維持原名，僅 `P03`~`P05` 帶 `_auto.md` 後綴。
   - `PlanStatusResolver.resolve_phase_file` 與 `PlanScanner`、`PlanVerifier`、`PlanArchiver` 原生雙軌相容 `<stem>.md` 與 `<stem>_auto.md`。
2. **內聯骨架速查表與單次到位寫入 (`Zero Redundant Reads & 1-Write-Per-File`)**：
   - `auto/SKILL.md` 內建 `P01`~`P06` 必填標頭與二級章節標題速查表，免除 `/auto` 期間逐一 `read_file` 讀取 `phase_01~05.md` 與模板之 11 次讀檔開銷。
   - 每個階段檔案嚴格僅寫入一次（`P01`~`P04` 直接寫 `Confirmed`、`P05_task_auto.md` 於編碼完成後直接寫 `Completed`、`P06_test_plan.md` 於自動化測試通過後直接寫 `Passed`），並於 `P06` 執行**單次彙總** `plan verify <plan> --log "..."`。
3. **跨檔單點定義去重與禁預寫實作碼 (`DRY Spec Reference & Signature-Only`)**：
   - 變更檔案清單單點定義於 `P02` §3；`P03` §2 僅寫 `def/class` 型別簽名與例外契約（嚴禁預貼函式實作程式碼）；任務拆解單點定義於 `P04` §4，`P05_task_auto.md` 僅列 1 行指標（$\le 25$ 行）。

### 5.3 適用範圍与三大熔斷防線 (Circuit Breakers)
- **適用範圍**：進行中之 **Full Track** 計畫或 **Umbrella** 活躍之 Full Track 子計畫 (`sub_XX`)；排除 `P00 Discussing` 與 **Fast Track**。
- **三大熔斷防線**：
  1. **零臆測熔斷 (Zero Speculation Gate)**：遇到任何需求不明或技術未知，立即停手提問。
  2. **偏差熔斷 (Deviation Gate)**：遇到 Major/Critical 架構或 API 偏差，立即停止並轉入 `/Discuss`。
  3. **P06 手動/UX 驗證絕對阻斷 (Mandatory UX Gate)**：CLI 自動化測試與支柱三 Pre-UX 盲審通過後，強制停步等待開發者人工/UX 驗收，絕對禁止自動結案。

---

## 6. 自動化測試規範技能 (`testing-sop`) 與三支柱 Subagent 隔離協定

### 6.1 自動化測試規範技能 (`testing-sop`)
`testing-sop` 為與 `documentation` 對偶之環境型技能，管轄專案之測試建置與回歸驗證：
- **六大自動化測試建置與回歸鐵律**：子系統 1:1 歸戶（禁止計畫名碎片檔）、實質副作用與正負雙向斷言（禁止空殼斷言與 mock 自身）、管線實機產出驗證（禁止靜態文檔 grep）、零歷史墓碑（舊 API 刪除時同步清理舊測）、100% 狀態隔離與沙盒零殘留、本體獨立性（零跨層反向耦合）。
- **Phase 06 雙重驗收守門**：守門 ①（子系統回歸全綠）+ 守門 ②（新增測試反模式自檢）。
- **`TESTING_SOP_STANDARDS` 錨點**：供專案注入專屬測試框架與沙盒規範。
- **存量測試集純化**：按需讀取 `references/test_suite_audit_and_purification.md` 執行 `T-01`~`T-06` 體檢與收斂。

### 6.2 唯讀 Subagent 委派協定（廣域探索與 Pre-UX 零劇透冷眼盲審）
針對高認知負荷場景，透過「僅傳計畫路徑盲審」與「Single-Writer 計畫檔保護」內化唯讀 Subagent 委派（而 `Phase 05` 編碼實作因跨模組任務間常具高耦合與上下文相依，統一維持由主視窗 Agent 直接實作，廢棄實作隔離開銷）：
1. **支柱一（`/research` 與 `/discuss` 唯讀廣域探索隔離）**：派發唯讀 Subagent 平行或單一檢索，回傳 150~300 Tokens 濃縮證據，主視窗維持乾淨 Context 撰寫報告或討論卡。
2. **支柱三（`Phase 06` Pre-UX 唯讀 Fresh-Eyes 冷眼盲審與 `Phase 07` 條件式複審）**：
   - **審查左移時機**：在完成自動化跑測、**即將向開發者提出手動 / UX 測試驗證請求前**，強制派發無偏誤的 Reviewer Subagent 進行客觀審查。
   - **零劇透盲審傳址**：不告知子代理本次計畫實作內容，僅提供計畫目錄路徑由子代理自行探索規格（`P01`/`P03`/`P04`）與版本控制變更（`git status --short`、`git diff HEAD` 及直讀 `Untracked` 新檔），杜絕提示詞錨定偏誤。
   - **純靜態唯讀禁跑測**：明確告知子代理嚴禁執行任何實機指令或測試運行，僅可運行唯讀工具進行靜態檢查；僅審查敷衍修補、測試反模式、需求遺漏與文檔未同步三類硬性契約，無缺失回傳 `REVIEW_STATUS: PASSED`。
   - **條件式複審**：進入 `Phase 07` 結案時，若 UX 驗收期間完全未更動生產或測試代碼，直接由主 Agent 執行常規文檔與註解審閱；若 UX 測試曾更動原始碼或核心邏輯，則強制再次派發支柱三 Subagent 進行二度冷眼盲審。

---

## 7. 互動式配置教練 (`/how-to-config-yscb`) 與實戰上手領航 (`/how-to-yscb`)

### 7.1 專案角色邊界錨點 (`PROJECT_ROLE_AND_BOUNDARIES`)
`AgentsStandards.md` 頂部（於 `## 1. 核心原則` 之前）提供獨立錨點 `` `__@{PROJECT_ROLE_AND_BOUNDARIES}__` ``。專案可於 `config/agents-workflow/contribute.json` 注入 `config://agents-workflow/snippets/project_role.md`，明確定義「① 專案角色與核心使命、② 第一方活躍開發範疇、③ 外部工具鏈與運行期黑盒邊界、④ 工作流物化唯讀空間」，使 Agent 於 `/context-init` 熱啟動首步即精準掌握主客體邊界，並對未配置專案自動靜默抹除（零殘留）。

### 7.2 專案空間自適應配置與跨模組組態體檢教練 (`/how-to-config-yscb`)
透過動態聚合錨點 `` `__@{HOW_TO_CONFIG_MODULES}__` `` 匯聚所有已安裝模組之 `assets/config_guide.md`，執行四步閉環：
1. **Step 1（自動空間探勘與多模組健康檢查）**：執行 `status`、`config list`、`uri check`、`contributes check`、檢查 `.gitignore` 是否忽略 `*.local.json`，並依各模組體檢指南逐一核對。
2. **Step 2（診斷報告與配置草案卡）**：支援**全綠健康短路 (All-Green Short-Circuit)**（全綠時不強行覆寫組態）與**第一方專案三位一體對齊 (First-Party Trinity Alignment)**（單次目錄探勘同步生成 `project_role.md`、`testing_guide.md` 與 `knowledge-db` `spaces.source.include` 草案，並嚴格區分 `config.project.json` 與 `config.local.json` 雙層階層）。
3. **Step 3（引導寫入與三步編譯發布守門）**：確認後寫入組態，並強制通過 `contributes check` $\to$ `agents-workflow compile`（0 Error / 0 Warning）$\to$ `agents-workflow release` 三步守門。
4. **Step 4（潔淨對話切換提示）**：提醒開發者開啟全新對話視窗以乾淨 Context 載入更新後的 `AGENTS.md` 與技能。

### 7.3 生態系互動式上手與實戰領航教練 (`/how-to-yscb`)
透過動態聚合錨點 `` `__@{HOW_TO_YSCB_MODULES}__` `` 匯聚所有已安裝模組之 `assets/usage_guide.md`：
1. **雙入口自適應領航**：無參數呼叫時提供已安裝模組能力總覽與 `A~D` 探索切角選單；帶具體問題呼叫時直接跳過選單給出精準解答與黃金連招。
2. **兩階段漸進式知識調度**：第一階段依內建 6 大計畫模式選型表與模組速查面板秒答；第二階段於開發者追問深層細節時，按需讀取各模組速查表底部的隨包手冊連結（`__#{module://<mod>/README.md}__`）。
3. **純唯讀教練護欄與新對話一鍵啟動指令塊**：教練視窗嚴禁直接修改代碼或建立計畫，需要配置時轉介 `/how-to-config-yscb`，準備正式開發時提供可直接複製貼上至新對話的啟動指令塊。

### 7.4 專案特化技能建置與 Layer 2 宣告式擴充工作流 (`/skill-creator`)
當專案已完成基礎組態對齊，欲進一步新增**專案特化技能**或**階段防呆規則**時，透過 `/skill-creator`（搭配單層參考手冊 `references/extension-guide.md`）執行四步建置與驗證閉環：
1. **步驟 1（三軌擴充智能分流 `3-Track Extension Triage`）**：依需求規模自動分流為 **軌跡 ①（純錨點注入 `Anchor-Only Injection`）**（於 `config://agents-workflow/snippets/<name>.md` 撰寫局部片段並注入 22 個既有 Stage 1 錨點之一，0 路由表膨脹）、**軌跡 ②（被動環境攔截型 Skill `Ambient Skill`）**（建立 `config://agents-workflow/skills/<name>/SKILL.md` 並注入 `AGENTS_SKILL_ROUTING` 表格列）或 **軌跡 ③（功能特化型 Skill `Feature Skill`）**（建立多步驟專項工作流技能）。
2. **步驟 2（錨點與 URI 探索及「擴充藍圖確認卡」守門）**：自動執行 `agents-workflow tokens` 與 `uri list` 並查閱 `extension-guide.md` 之 22 個 Stage 1 錨點地圖，向開發者呈遞「🛠️ /SkillCreator 專案擴充藍圖確認卡」並 End Turn 等待拍板。
3. **步驟 3（合規第一層資產生成與雙軌路徑封裝）**：於第一層扁平路徑（`config/agents-workflow/skills/<name>/SKILL.md` 或 `snippets/<name>.md`）生成資產；指向同技能內部 `references/` 使用標準相對路徑 `./references/...`，指向跨技能或專案目錄強制使用單反引號包覆之 Stage 2 語意 URI。
4. **步驟 4（三步嚴格編譯驗證守門）**：最小增量更新 `config/agents-workflow/contribute.json`，強制依序通過 `contributes check`（0 Error）$\to$ `agents-workflow compile`（0 Error / 0 Warning）$\to$ `agents-workflow release` 物化同步至目標平台。


