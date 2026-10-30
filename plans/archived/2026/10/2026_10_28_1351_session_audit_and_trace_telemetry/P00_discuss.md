# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：Session 隱形摩擦自檢技能與三級軌跡提取機制 (`session_audit_and_trace_telemetry`)  
> 建立日期：2026-10-28  
> 所屬主計畫：獨立計畫 (Standalone)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (High)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：針對發想團隊提出之 `session-audit`（Session 效益、決策瑕疵與隱形摩擦自檢技能與三級軌跡提取 CLI）藍圖立項，解決多 Active Targets（多 `release_targets` 宿主／Subagent 與多進行中計畫）之精準定錨問題，並將 CLI Telemetry 上提至 `core` 管理範疇與對應快取目錄（`cache://core/`）。
- **核心目標**：
  1. **`core` 層級統一 CLI 飛行紀錄器（Telemetry in `core`）**：將 CLI 調用軌跡管理上提至 `core` 範疇（新增 `core/telemetry.py` 並由 [`core/commands/dispatcher.py`](file:///workspace/ys-codebase/ys_codebase/source/core/core/commands/dispatcher.py) 統一攔截路由錯誤、參數解析錯誤、`_try_hot_dispatch` 熱派發與 `dispatch_local` 冷派發），統一落盤於 **`cache://core/telemetry.jsonl`**（實體為 `ys_codebase/.cache/core/telemetry.jsonl`），維持 `core` 微內核對上層模組之零耦合。
  2. **三級漸進式軌跡提取與多 Target 定錨引擎（`agents-workflow session-trace`）**：實作 `python yscb.py agents-workflow session-trace [--plan <dir>] [--transcript <path>] [--since <min>] [--json]`，整合：
     - **Tier 1（多宿主 `release_targets` 本地 `.jsonl` 三層信標定錨與解析）**：支援 `--transcript` 顯式指定；未指定時掃描已啟用 `release_targets` 對應日誌目錄之近期 `.jsonl`，透過尾端 64KB「工作區路徑指紋 + `session-trace` 尾行自指信標」精準排除 Subagent 與其他視窗；歧義時拒絕盲猜並列舉候選。
     - **Tier 2（`cache://core/telemetry.jsonl` 時間窗切片 + 計畫 `mtime` 逆序消歧 + `git diff`）**：從 `core.telemetry` 依當前 Session 起點切片提取非零退出碼、重試與連續搜尋空轉（$\ge 3$ 次）；針對單一活躍計畫（或剛歸檔計畫）比對 `P00`~`P07` `mtime` 與 `changelog.md` 階段時間戳，並結合 `changelog.md` (`REVISION`/`DECISION`) 與 `revision_log.md` 精確區分「合規規格回寫（`VALIDATED_BACKPROP`）」與「未申報之跨階段暗中偷改（`SILENT_BACKPATCH`）」。
     - **Tier 3（In-Context 結構化記憶逆向審訊 Fallback）**：當無外部 `.jsonl` 且無異常 Telemetry 時，輸出結構化逆向審訊提示與查核表。
  3. **唯讀事後法醫解剖技能（`/session-audit`）**：於 `agents-workflow` 新增內建主動技能 `assets/skills/session-audit/SKILL.md`，強制執行「絕對唯讀安全隔離（Strict Read-Only Quarantine）」、「五大硬性摩擦訊號盤點」與「A/B/C/D 四象限根因分類樹」，並於發現高價值缺陷時輸出 `[Harvest Candidate]` 建議。
- **邊界排除 (Explicitly Excluded)**：
  - 本計畫聚焦於 Stage 1 觀測與自檢機制（`core` Telemetry + `session-trace` CLI + `/session-audit` Skill），**不包含** Stage 2 雙盲沙盒 A/B 評測執行器與 Stage 3 `TrackSpec` 平台化解耦。
  - `/session-audit` 執行期間嚴禁自動修改任何專案業務源碼、設定檔或既有 `P00`~`P07` 規格內文。
- **架構影響範圍**：
  - `ys_codebase/source/core/core/telemetry.py`、`core/commands/dispatcher.py`、`core/__init__.py`（`core` 層級 Telemetry 記錄、滾動截斷與讀取 API，落盤於 `cache://core/telemetry.jsonl`）。
  - `ys_codebase/source/agents-workflow/agents_workflow/session_trace.py`（三級軌跡提取、多 Target 信標定錨與五大摩擦訊號偵測引擎）。
  - `ys_codebase/source/agents-workflow/scripts/cli.py`、`contributes/core.json`、`contributes/agents-workflow.json`（掛載 `session-trace` 指令與導出 `session-audit` 技能）。
  - `ys_codebase/source/agents-workflow/assets/skills/session-audit/SKILL.md`（唯讀自檢技能手冊）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] CLI Telemetry 上提至 `core` 管理範疇並落盤於 `cache://core/telemetry.jsonl`**：
  - 遵循 `core` 微內核職責邊界與去耦合原則，CLI 執行軌跡屬於核心派發基建，由 `core/telemetry.py` 與 [`core/commands/dispatcher.py:dispatch`](file:///workspace/ys-codebase/ys_codebase/source/core/core/commands/dispatcher.py#L461) 統一管理並寫入 `cache://core/telemetry.jsonl`（實體路徑 `ys_codebase/.cache/core/telemetry.jsonl`）。
  - 單筆 JSONL 結構為 `{ts, module, cmd, args, exit_code, duration_ms, mode, cwd, error_hint}`（涵蓋 `router_err`、`option_err`、`hot`、`local` 四種派發結果與首行錯誤摘要）。
  - **防護與降噪**：當 `YSCB_TEST_SANDBOX == "1"`（且未設定測試覆寫變數 `YSCB_TELEMETRY_PATH`）、呼叫 `-h`/`--help` 或呼叫 `session-trace` 自身時自動略過；檔案超過 512 KB 時自動滾動保留最新 1,500 筆紀錄。
- **[P00:DR-02] 多宿主 `release_targets` 與多視窗／Subagent 之「三層信標定錨（3-Step Beacon Anchoring）」與時間窗切片**：
  - **Tier 1 `.jsonl` 定錨順序**：
    1. **顯式指定（`--transcript <path>`）**：宿主環境若已知當前對話 Transcript 路徑（如 Antigravity System Prompt 宣告路徑），由 Agent 直接傳入，100% 零誤差命中主對話。
    2. **尾行自指信標 + 工作區指紋匹配**：未傳 `--transcript` 時，掃描已配置 `release_targets`（`antigravity`, `claude`, `codex`）對應本機日誌目錄中近期活躍之 `.jsonl` 尾端 64KB，同時檢驗「包含當前 `project_root` 路徑」與「尾端出現 `session-trace` / `/session-audit` 觸發信標」，精準過濾已結束之 Subagent 與其他專案視窗。
    3. **多候選歧義拒絕盲猜**：若離線分析無尾行信標且命中多份 `.jsonl`，依零臆測原則列出候選清單供指定，並先行輸出 Tier 2 結果。
  - **Telemetry 時間窗自動切片（Session Window Slicing）**：優先以 Tier 1 鎖定之 `.jsonl` 首筆時間戳為起點過濾 `cache://core/telemetry.jsonl`；若無 Tier 1 則以最近一次間隔 $> 30$ 分鐘之熱啟動指令或目標計畫 `changelog.md` 首筆時間為起點（支援 `--since <min>` 覆寫）。
- **[P00:DR-03] 多活躍計畫／剛歸檔計畫定位與跨階段 `mtime` 逆序消歧機制**：
  - **目標計畫定位**：單一活躍計畫（或 `Umbrella` 下唯一 `In Progress` 之 `sub_XX`）自動綁定；若存在 $>1$ 個活躍計畫且未傳 `--plan`，於計畫審計區段輸出明確提示請使用者以 `--plan` 指定（不中斷 CLI 與 `.jsonl` 軌跡提取）；若當前為 0 個活躍計畫，自動檢查 `workflow.archived://` 下最近 30 分鐘內剛歸檔之計畫。
  - **合法規格回寫 vs. 暗中偷改消歧**：當前期檔案（`P01`~`P03`）之 `mtime` 晚於後期階段（如 `P04`/`P05`）在 `changelog.md` 之完成時間戳（誤差 $> 5$ 秒）時，同步檢查 `changelog.md` 是否存在對應之 `REVISION`/`DECISION` 紀錄或存在 `revision_log.md`——有紀錄標為 `VALIDATED_BACKPROP`（合規反向回寫），無紀錄則抓出 `SILENT_BACKPATCH`（未申報之暗中偷改）。
- **[P00:DR-04] `/session-audit` 技能契約與五大摩擦訊號 -> 四象限根因分類樹**：
  - 機械式提取 `MULTI_EDIT_CHURN`（同檔多次修改）、`TOOL_MISS_AND_RETRY`（指令失敗與連續搜尋 $\ge 3$ 次）、`SILENT_BACKPATCH`（未申報跨階段偷改）、`GATE_BOUNCE`（驗證退件）、`CONTEXT_WASTE`（同檔重複讀或未檢索連續盲讀 $\ge 4$ 檔）五大硬訊號，嚴格歸入 Type A（提示詞/SOP 歧義）、Type B（ACI 工具/檢索斷層）、Type C（任務本質探索）、Type D（模型注意力滑脫），並維持 100% 唯讀安全隔離。

---

## 3. 開放議題與確認紀錄

- **開放議題**：無。
- **確認紀錄**：
  1. 2026-10-28：開發者指示對 `session_audit_and_trace_telemetry.md` 立項。
  2. 2026-10-28：開發者確認多 Active Targets 定錨機制，並拍板將 Telemetry 上提至 `core` 管理範疇、記錄於 `cache://core/telemetry.jsonl`。
