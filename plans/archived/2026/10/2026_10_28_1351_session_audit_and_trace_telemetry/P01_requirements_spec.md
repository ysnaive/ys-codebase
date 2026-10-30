# 需求規格說明書 (Requirements Specification)

> 功能名稱：Session 隱形摩擦自檢技能與三級軌跡提取機制 (`session_audit_and_trace_telemetry`)  
> 建立日期：2026-10-28  
> 所屬主計畫：獨立計畫 (Standalone)  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (High)  

> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `core` 層級統一 CLI 飛行紀錄器 (`core/telemetry.py` & `dispatcher.py`) | 1. 於 `core` 新增 `core/telemetry.py` 並匯出於 `core/__init__.py`，統一落盤於 **`cache://core/telemetry.jsonl`**（實體路徑為 `ys_codebase/.cache/core/telemetry.jsonl`），確保 `core` 微內核對 `agents-workflow` 零耦合 (`[P01:DR-01]`)。<br/>2. 於 [`core/commands/dispatcher.py:dispatch`](file:///workspace/ys-codebase/ys_codebase/source/core/core/commands/dispatcher.py#L461) 外層攔截計時，記錄單行 JSONL `{ts, module, cmd, args, exit_code, duration_ms, mode, cwd, error_hint}`，完整涵蓋路由錯誤 (`router_err`)、參數解析錯誤 (`option_err`)、熱派發 (`hot`) 與冷派發 (`local`)。<br/>3. `_try_hot_dispatch()` 串流讀取時自動擷取首行 `stderr` 或 `[Error]`/`[FAIL]`/`[BLOCKER]` 摘要（上限 200 字元）填入 `error_hint`。 | P0 | [P00:DR-01] |
| **FR-02** | 多宿主 `release_targets` 與多視窗之 Tier 1 `.jsonl` 三層信標定錨 | 1. `session-trace` 支援 `--transcript <path>` 顯式指定 `.jsonl` 路徑（優先級 1，100% 鎖定主對話）。<br/>2. 未傳入 `--transcript` 時，自動讀取 `agents-workflow` 組態之 `release_targets`（支援 `antigravity`, `claude`, `codex`），掃描各目標對應本機日誌目錄中近期活躍之 `.jsonl` 尾端 64KB，以「工作區路徑指紋 (`project_root`) + 尾行自指信標 (`session-trace` / `/session-audit`)」精準排除 Subagent 與其他專案視窗（優先級 2，`[P01:DR-02]`）。<br/>3. 成功鎖定時，濾除大型檔案輸出內容，提取失敗/重試之 Tool Calls、同檔多次 Edit 紀錄與事發前後一輪 `<thinking>` 摘要。 | P0 | [P00:DR-02] |
| **FR-03** | Tier 2 原生 Telemetry 時間窗切片與跨階段 `mtime` 逆序消歧 | 1. **時間窗自動切片**：優先以 Tier 1 `.jsonl` 首筆時間戳 $T_{\text{start}}$ 過濾 `cache://core/telemetry.jsonl`；若無 Tier 1 則以最近一次間隔 $> 30$ 分鐘之熱啟動指令或目標計畫 `changelog.md` 首筆時間為起點（支援 `--since <minutes>` 覆寫）。<br/>2. **跨階段修改消歧**：掃描目標計畫目錄下 `P00`~`P07` 之 `mtime` 與 `changelog.md` 階段完成時間戳，當前期檔案在後續階段完成後被修改（誤差 $> 5$ 秒）時，同步檢查 `changelog.md` 是否有對應之 `REVISION`/`DECISION` 紀錄或存在 `revision_log.md`——有紀錄標記為 `VALIDATED_BACKPROP`（合規反向回寫），無紀錄則標記為 `SILENT_BACKPATCH`（未申報暗中偷改）。 | P0 | [P00:DR-02], [P00:DR-03] |
| **FR-04** | 五大硬性摩擦訊號機械偵測與 Tier 3 逆向審訊保底 | 1. `session-trace` 自動聚合併輸出五大摩擦訊號：`MULTI_EDIT_CHURN`（同檔多次修改 $\ge 2$ 次且穿插其他操作）、`TOOL_MISS_AND_RETRY`（`exit_code != 0`、緊隨 `-h` 自省、或連續 `knowledge-db search` $\ge 3$ 次）、`SILENT_BACKPATCH`（未申報跨階段偷改）、`GATE_BOUNCE`（`plan verify` / `dev check` / `dev test` / `contributes check` 非 0 退件）、`CONTEXT_WASTE`（同檔重複讀取 $\ge 2$ 次或未檢索連續翻讀 $\ge 4$ 個源碼檔）。<br/>2. 當 Tier 1 與 Tier 2 均無外部檔案與異常紀錄時，自動輸出 `[Fallback: In-Context Mode]` 與結構化逆向審訊檢核表（Tier 3）。 | P0 | [P00:DR-03], [P00:DR-04] |
| **FR-05** | `agents-workflow session-trace` CLI 契約與 `/session-audit` 唯讀技能導出 | 1. 於 `agents-workflow` 之 `contributes/core.json` 與 `scripts/cli.py` 註冊 `session-trace` 指令（支援 `--plan`, `--transcript`, `--since`, `--limit`, `--json`）。<br/>2. 建立 `assets/skills/session-audit/SKILL.md` 並於 `contributes/agents-workflow.json` 與 `_manifest.md` 註冊導出（內建純 Skill 擴充至 18 個）及 `SESSION_AUDIT_STANDARDS` Token 錨點，強制規範「絕對唯讀隔離」、「A/B/C/D 四象限根因分類樹」與 `[Harvest Candidate]` 建議卡。 | P0 | [P00:DR-04] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 多宿主 `.jsonl` 離線分析無尾行信標且匹配到多份工作區日誌 | 遵循零臆測原則拒絕盲猜，於 `session-trace` 輸出匹配之候選 `.jsonl` 清單（含宿主類型、檔案路徑、修改時間），並自動先行輸出 Tier 2 與 Tier 3 分析結果。 |
| **EC-02** | `plans/` 下同時存在多個活躍計畫（或 0 個活躍計畫如剛歸檔結案） | 1. 多活躍計畫且未傳 `--plan`：不中斷 Tier 1 / Tier 2 CLI 軌跡分析，於計畫審計區段輸出明確提示請以 `--plan <name>` 指定。<br/>2. 0 活躍計畫：自動檢查 `workflow.archived://` 下最近 30 分鐘內剛歸檔之計畫目錄進行 `mtime` 審計；若亦無則僅略過計畫 `mtime` 區段，正常回傳 CLI 與 `.jsonl` 摩擦訊號。 |
| **EC-03** | 沙盒測試 (`YSCB_TEST_SANDBOX == "1"`)、`-h`/`--help` 或 `session-trace` 自身呼叫 | `core/telemetry.py` 預設略過沙盒測試（除非顯式設定 `YSCB_TELEMETRY_PATH` 供單元測試驗證）、略過 `--help` 查詢與 `session-trace` 自身呼叫，杜絕測試噪音與自檢動作污染觀測紀錄。 |
| **EC-04** | `cache://core/telemetry.jsonl` 檔案體積長期累積或寫入權限異常 | 單檔超過 `512 KB` 時自動滾動截斷並保留最新 `1,500` 筆合法 JSONL 紀錄；任何磁碟 I/O 例外均以 `try...except Exception: pass` 靜默吞除，保證 100% 不阻塞或中斷正常 CLI 指令執行。 |
| **EC-05** | 宿主沙盒禁止存取 `$HOME` 下之 `.claude` / `.codex` / `.gemini` 目錄或 `.jsonl` 行損毀 | Tier 1 探測與逐行 JSON 解析全程防護 `OSError`、`PermissionError` 與 `json.JSONDecodeError`，單行損毀自動跳過，目錄不可讀時無感降級至 Tier 2（退出碼維持 `0`）。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能與低延遲 | `core/telemetry.py` 單次 CLI 尾端追加寫入耗時 $\le 2\text{ms}$；`session-trace` 讀取與分析執行時間 $\le 150\text{ms}$。 |
| **NFR-02** | 上下文經濟與唯讀安全 | `session-audit/SKILL.md` 篇幅控制在 $\le 150$ 行；`session-trace` 輸出之 `<thinking>` 與報錯摘要必須強制截斷（單筆 $\le 300$ 字元），防止長日誌灌爆 Agent Context Window。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` Stage 2 語意 URI 單反引號包裹鐵律（參見 `docs/agents-workflow/FACTORY_PIPELINE.md` `FT-14`）**：撰寫 `assets/skills/session-audit/SKILL.md` 時，所有 `__#{uri}__` 與 `__${uri}__` 佔位符必須以單反引號 `` `...` `` 包裹，嚴禁裸露書寫以免觸發 `[compiler:warning]`。
- **`[!NOTE]` `core` 微內核零工作流耦合紅線（參見 `CHANGELOG.md` `sub_01_core_microkernel_and_tests` `C-01`）**：`core/telemetry.py` 與 `core/commands/dispatcher.py` 嚴禁硬編碼 `agents-workflow` 字串或路徑，所有紀錄一律歸口於 `cache://core/telemetry.jsonl`。
- **`[!NOTE]` `contributes/_manifest.md` 雙向契約守門**：於 `contributes/agents-workflow.json` 新增 `session-audit` 導出與 `SESSION_AUDIT_STANDARDS` Token 時，必須同步更新 `ys_codebase/source/agents-workflow/contributes/_manifest.md` 以通過 `dev check agents-workflow`。

