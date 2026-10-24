# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：sub_01_python_aci_toolchain  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：依據技術路線圖 [roadmap.md](./roadmap.md)，實作 `agents-workflow` Python 工具鏈 (ACI) 強化與狀態機下沉演進（`sub_01_python_aci_toolchain`）。
- **核心目標**：
  1. **M1（確定性狀態領航 + `--resume` 原子閱後即焚）**：擴充 `PlanStatusResolver` / `PlanScanner` 與 `plan status [--plan <plan_name_or_subpath>] [--resume]`，自動推導目標計畫（含自動深入 Umbrella 活躍之 `sub_XX` 子計畫）下一步應執行階段與必讀參考檔路徑 (`required_reference_path`)；當傳入 `--resume` 且存在 `handoff.md` 時，完整輸出快照內容並立即呼叫 `os.unlink()` 物理刪除（未傳 `--resume` 時維持 100% 純唯讀）；精簡 `continue/SKILL.md` 優先調用 `plan status --resume` 並保留極簡沙盒唯讀 Fallback。
  2. **M2（單階段左移檢核 + `P01<->P06` 追溯差集比對 + 自癒型報錯）**：擴充 `PlanVerifier` 與 `plan verify [plan_name_or_subpath] [--phase <P00..P07|current|all>]` 支援單階段與雙檔協同檢核（`P02` 檢核 `P06_test_plan.md` 存在性、`P04` 檢核 `P06` 狀態達 `Confirmed` 以上）；實作 `P01_requirements_spec.md` (`FR-\d+`/`EC-\d+`/`NFR-\d+`) 與 `P06_test_plan.md` 集合差集比對（預先剝除 Fenced Code Blocks、HTML 註解與 `~~...~~` 刪除線）；所有 `FAIL`/`WARN` 診斷均附帶可操作修復指引 (`Actionable Fix Hint`)。
  3. **M3（`changelog.md` 免讀盲寫追加與伴隨鷹架自癒）**：於 `plan verify` 擴充 `--log "<摘要>" [--type PHASE|DECISION|REVISION] [--model "<ModelName>"]`（並嚴格執行四步管線時序：Step 1 檢核主體檔 $\to$ Step 2 自動補齊缺失之 `changelog.md` 與 `P02` 伴隨之 `P06_test_plan.md (Draft)` $\to$ Step 3 雙檔與全項合規檢核 $\to$ Step 4 僅在 100% `PASS` 時自動以系統時間戳寫入 `changelog.md` 並具 `(類型, 摘要)` 冪等防重入保護）；伴隨檔模型紀錄僅取 `--model` 或當下同階段主體檔標頭（否則填 `Unknown`，嚴禁跨階段回溯舊檔）；同步更新 `yscb-cli-guide` 與 `development-sop` 規範 `--log` 內文禁用雙引號 `"` 與反引號 `` ` ``。
- **邊界排除 (Explicitly Excluded)**：
  - 主體規格檔（`P00`~`P07`、`fast_track_plan.md`、`revision_log.md` 等）維持宿主原生 `write_file` 單次寫入，不引入強制預建空白主體檔之重度 CLI 步驟。
  - `/todo` 與 `/roadmap` 雙層體系及 `roadmap.md`/`todo.md` 白名單歸屬 `sub_02`；Subagent 三支柱委派協定歸屬 `sub_03`。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/status.py`
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/scanner.py`
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/verifier.py`
  - `ys_codebase/source/agents-workflow/scripts/cli.py`
  - `ys_codebase/source/agents-workflow/contributes/core.json`
  - `ys_codebase/source/agents-workflow/assets/skills/continue/SKILL.md`
  - `ys_codebase/source/agents-workflow/assets/skills/development-sop/SKILL.md` 及相關阶段參考手冊

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 保留主體規格檔單次原生寫入，下沉狀態領航、伴隨檔自癒與 `changelog.md` 盲寫追加（方案 3）**：主體規格文件維持原生 `write_file` 一次寫定（免雙重讀改 I/O）；將狀態推導與 `handoff.md` 原子銷毀收斂至 `plan status --resume`，將階段合規檢核、伴隨檔初始化（`changelog.md`、`P06 Draft`）與 `changelog.md` 免讀盲寫追加收斂至 `plan verify --phase ... --log ...`。
- **[P00:DR-02] 四步執行管線時序與冪等防重入 (`Step 1~4 Pipeline & Idempotency`)**：執行 `plan verify --phase P02 --log "..."` 時，嚴格依序執行「1. 主體檔合規檢核 $\to$ 2. 伴隨檔（`P06 Draft`、`changelog.md`）自動補齊 $\to$ 3. 雙檔協同與追溯差集檢核 $\to$ 4. 100% PASS 方追加日誌（且比對首筆 `(類型, 摘要)` 實現冪等防重入）」。
- **[P00:DR-03] 伴隨檔模型紀錄防回溯與 `P01` 刪除線/註解預過濾**：自動生成伴隨檔時，`> 模型：` 僅取 `--model` 或當下同階段主體檔標頭（否則填 `Unknown`，嚴禁回溯 `P00` 等舊檔）；提取 `P01` 需求 ID (`FR/EC/NFR`) 前預先剝除程式碼區塊、HTML 註解與 `~~...~~` 刪除線，防止誤判孤兒 ID。
- **[P00:DR-04] 終端單行引號與反引號逃逸防呆**：於 CLI 指南與 SOP 規範 `--log "<摘要>"` 內文嚴禁包含雙引號 `"` 與反引號 `` ` ``，一律改用單引號 `'...'` 或方括號 `[...]`。

---

## 3. 開放議題與確認紀錄

- 需求與技術細節已於 [python_aci_toolchain_roadmap.md](../../roadmap/python_aci_toolchain_roadmap.md) 100% 完備定調，無待決開放議題。

