# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：`/auto` 單一區間規格任務檔 (`PXX-05_auto.md`) 與 `agents-workflow` 檢索／恢復／檢核精煉  
> 建立日期：2026-11-01  
> 所屬主計畫：2026_11_01_1054_auto_plan_and_workflow_refinement  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 經實證分析，現行 `/auto` 模式分寫 5 份獨立 `P01_auto.md` ~ `P05_auto.md` 存在跨檔標頭、檔案表與 TASK 清單重複抄寫問題（單一計畫消耗約 26.5 KB Output Token，與標準模式相比幾乎零節省）。希望改採單一動態起點區間合併檔 **`PXX-05_auto.md`**（Agent 須將 `XX` 替換為開始 `/auto` 的階段，例如 `P00` 討論完開 `/auto` 即為 `P01-05_auto.md`），但原 `P01`~`P05` 模板規定的核心工程契約資訊皆須保留且單點定義不重複。
  - 同步打包解決同屬 `agents-workflow` 範疇的關聯待辦（選項 A：`TODO-10`、`TODO-13`，外加 `plan verify` 硬編碼絕對路徑可攜性警告與 `plan status` 已完成計畫歸檔提醒）。
- **核心目標**：
  1. **`PXX-05_auto.md` 動態區間合併模板與 `/auto` 技能升級**：建立 `assets/templates/PXX-05_auto.md` 權威模板並註冊至 `contributes/agents-workflow.json`，保留原 `P01`~`P05` 全部核心契約（`FR/EC/NFR`、`[P0X:DR-XX]`、架構拓撲、受影響檔案表、`Signature-Only` API 簽名與例外契約、定稿審查與文檔衝擊表、靈魂拷問、單一合併版 `TASK-XX` 勾選與實作偏差表），徹底消除跨 5 檔重複寫入；支援動態起點 `P01-05_auto.md` ~ `P04-05_auto.md`（若自 `P05` 啟動則為 `P05_task_auto.md` 或 `P05-05_auto.md`），並對歷史已歸檔之 `P01_..._auto.md` ~ `P05_..._auto.md` 保持 100% 向下相容。
  2. **`plan search` 檢索排序、時間衰減與 Umbrella 子計畫修復 (`TODO-10` Part 1 & 2)**：
     - 修復 `searcher.py` 在 Umbrella 計畫下 `search_drs` 因 `dedup_key = (plan.name, dr_id)` 跨 `sub_XX` 誤刪同名 DR 的 Bug（改納 `relative_to(plan)`），放寬無冒號 `**[P0X:DR-XX]**` 提取正則，並修復 `search_full_text` 遺失 `sub_XX/` 相對路徑的問題。
     - 強化 `plan search` 排序：賦予 `P00`、`R{NN}`、`P07`、`fast_track_plan`、`revision_log` 與 `[DR-` 決策更高權重，引入計畫時間戳衰減（越近期計畫優先），並降權歷史歸檔之 `P01`~`P04` / `_auto.md` 過程檔；為 `plan search` 新增 `--full` 與 `--json` 選項，並將預設表格路徑截斷改為左側截斷（`...sub_XX/P00_discuss.md`）保留關鍵尾端資訊。
  3. **`plan status --resume` 確定性熱上下文恢復膠囊與歸檔提醒 (`TODO-10` Part 3 & `TODO-14` Part 2)**：
     - 當執行 `plan status --resume` 且目標計畫無 `handoff.md` 時，由 `scanner.py` / `status.py` 自動從既有 `P00`、`P02`/`P05`、`PXX-05_auto.md`、`fast_track_plan.md` 或 `revision_log.md` 確定性抽取 300~500 tokens 的「熱恢復膠囊（Recovery Capsule）」（含核心 DR、異動檔案與進度摘要）。
     - 當 `plan status` 掃描發現 `plans/` 根目錄下存在已 `Completed` 或 `Concluded` 的滯留計畫時，自動於輸出尾端顯示建議執行 `plan archive` 的提醒。
  4. **`plan verify` 反向回寫檢核與絕對路徑可攜性警告 (`TODO-10` Part 4 & `TODO-12` Part 2)**：
     - 支援 `PXX-05_auto.md` 的結構、標頭自癒、必選章節（依起始階段 `XX` 動態判定必選章節集合）與 `FR/EC/NFR` $\leftrightarrow$ `P06_test_plan.md` 1:1 追溯檢核。
     - 區分人工逐步簽核之 `P02`/`P03` 與 `PXX-05_auto.md` 的後期規格同步檢核；掃描計畫 `.md` 內若含硬編碼 `file:///` 或本機磁碟機絕對路徑（如 `C:/`、`D:/`）時發出可攜性警告（Warning，不阻斷舊檔但提醒修正）。
  5. **`compiler.py` `[DN-AW-03]` 行內路徑變數反引號保留修復 (`TODO-13`)**：
     - 修正 `compiler.py:_replace_in_code_span`，當 `PROJECT_URI_EXACT_REGEX` 未帶 `anchor`（即純 `` `__${uri}__` `` 行內路徑變數，而非 `` `[text](__${uri}__)` `` 連結）時保留外層反引號 `` `{resolved}` ``。
- **邊界排除 (Explicitly Excluded)**：
  - 不包含 `core` 模組之 `pip_manager.py` / `cmd_restore` 修改（保留於 `TODO-07`、`TODO-12`）與 `knowledge-db` 模組之 `SpaceDef.weight` / `linker.py` / `treesitter.py` 修改（保留於 `TODO-08`、`TODO-09`、`TODO-14`、`TODO-15`），本次 100% 聚焦於 `agents-workflow` 模組閉環。
- **架構影響範圍**：
  - `ys_codebase/source/agents-workflow/assets/templates/PXX-05_auto.md`（新建）
  - `ys_codebase/source/agents-workflow/contributes/{agents-workflow.json, core.json}`
  - `ys_codebase/source/agents-workflow/agents_workflow/plans/{_common.py, status.py, scanner.py, _verifier_specs.py, _verifier_healer.py, verifier.py, searcher.py, _trace_parser.py}`
  - `ys_codebase/source/agents-workflow/agents_workflow/compiler.py`
  - `ys_codebase/source/agents-workflow/scripts/cli.py`
  - `ys_codebase/source/agents-workflow/assets/skills/{auto, development-sop, continue}/`
  - `ys_codebase/source/agents-workflow/tests/` 與 `docs/agents-workflow/`

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] `PXX-05_auto.md` 動態區間合併規範與章節結構設計**：
  - **結論**：廢除在 `/auto` 模式下分別建立 5 個獨立 `P01_auto.md` ~ `P05_auto.md` 的做法，改為建立單一合併檔 **`P{XX}-05_auto.md`**（其中 `{XX}` 為觸發 `/auto` 時的起始生成階段，例如在 `P00` `Confirmed` 後觸發即為 `P01-05_auto.md`；若在人工定案 `P02` 後觸發則為 `P03-05_auto.md`）。
  - **核心資訊零流失與去重**：模板完整涵蓋 5 大核心區段（`## 1. 需求規格與邊界契約 (P01)`、`## 2. 架構設計與異動檔案清單 (P02)`、`## 3. 介面契約與 API 簽名 (P03)`、`## 4. 定稿審查與文檔衝擊規劃 (P04)`、`## 5. 實作任務清單與偏差紀錄 (P05)`），將原先重複於 `P04 §4` 與 `P05 §1` 的 `TASK-XX` 清單合併於 `## 5`，並在單次實作完成後直接以 `> 狀態：Completed` 與 `- [x]` 一次性寫入落檔。
  - **動態章節檢核與向下相容**：`PlanVerifier` 根據檔名 `P{start}-05_auto.md` 的 `{start}`（`01`~`05`）動態檢查對應之 `(P0{i})` 區段與追溯鏈（如 `P01-05_auto.md` 檢查 `P01`~`P05` 全區段並提取 `FR/EC/NFR` 與 `P06` 比對；`P03-05_auto.md` 則從人工 `P01_requirements_spec.md` 提取 `FR/EC/NFR`，並對 `P03-05_auto.md` 檢查 `P03`~`P05` 區段）。同時 `status.py` 與 `verifier.py` 保留對舊版獨立 `P01_..._auto.md` ~ `P05_..._auto.md` 的識別相容，確保歷史歸檔計畫 100% 正常解析。
- **[P00:DR-02] `plan search` 檢索排序、時間衰減、Umbrella 路徑修復與 `--full`/`--json` 擴充 (`TODO-10`)**：
  - **結論**：
    1. 修正 `PlanSearcher.search_drs` 的去重鍵為 `(plan.name, str(md_file.relative_to(plan)), dr_id)`，根除 Umbrella 主計畫下跨 `sub_XX` 同名 `[P00:DR-01]` 碰撞丟失問題；將列表式 DR 提取正則放寬為支援 `-\s*\*\*([^*]*?DR[^*]*?)\*\*\s*(?:[:：]\s*|\s+)(.+)`（相容無冒號格式）；修正 `search_full_text` 之 `rel_path` 為 `str(md_file.relative_to(plan)).replace("\\", "/")`。
    2. 在 `search_drs` 與 `search_full_text` 引入「檔案角色權重 + 計畫時間序」排序：高價值決策與總結檔（`P00_discuss.md`、`RXX_*.md`、`P07_walkthrough.md`、`fast_track_plan.md`、`revision_log.md`、`umbrella_overview.md`）優先於中間過程檔（`P01`~`P05` 及 `_auto.md`），同級內依計畫時間戳由新到舊（Newest First）排序。
    3. 於 `contributes/core.json` 與 `scripts/cli.py:plan_search` 新增 `--full` 與 `--json` 旗標；預設表格顯示將 `source_file` 改為左側截斷（`"..." + src[-37:]`）以確保完整顯示 `sub_XX/P00_discuss.md`。
- **[P00:DR-03] `plan status --resume` 無 `handoff.md` 時之確定性熱恢復膠囊與滯留歸檔提醒 (`TODO-10` & `TODO-14`)**：
  - **結論**：
    1. 於 `scanner.py` / `status.py` 實作確定性 `build_recovery_capsule(plan_dir)`：當執行 `plan status --resume` 且無 `handoff.md` 時，自動從計畫內既有文件抽取「已拍板 DR 摘要（最多 5 筆）」、「受影響檔案清單（最多 8 筆）」與「任務完成度 / 下一步待辦」，合成精簡膠囊直接輸出於終端。
    2. 於 `scripts/cli.py:plan_status` 輸出現有計畫表格後，若偵測到頂層計畫狀態為 `Completed` 或 `Concluded`，自動輸出 `[提示] 偵測到 N 個已結案計畫仍滯留於 plans/，建議執行 'python yscb.py agents-workflow plan archive <plan_name>' 歸檔以維持知識庫檢索純淨度`。
- **[P00:DR-04] `compiler.py` `[DN-AW-03]` 反引號保留與 `plan verify` 可攜性／反向回寫檢核 (`TODO-13` & `TODO-12`)**：
  - **結論**：
    1. 在 `compiler.py:_replace_in_code_span` 中，當 `m_proj_exact = PROJECT_URI_EXACT_REGEX.fullmatch(inner.strip())` 匹配成功時，僅在帶有 `anchor`（即 `__$[text]{uri}__` 轉為 Markdown 連結 `[text](path)`）時剝除外層反引號；若無 `anchor`（即純 `` `__${uri}__` `` 路徑變數），返回 `` f"`{resolved}`" `` 保留行內代碼格式。
    2. 在 `verifier.py` 新增可攜性檢查：掃描計畫 `.md` 檔案若包含 `file:///` 或 Windows 磁碟機絕對路徑（如 `(?i)\b[c-z]:[/\\]`），於驗證報告附加 `[PORTABILITY WARNING]` 提示改用專案相對路徑；針對人工簽核之標準 `P02`/`P03`，若 `P05_task.md` 記載有 `Major` 實作偏差而 `P02`/`P03` 未同步更新，發出反向回寫提醒（`PXX-05_auto.md` 則因同檔合一免跨檔回寫）。

---

## 3. 開放議題與確認紀錄

- 已由開發者確認採納 `PXX-05_auto.md` 動態區間合併設計並打包選項 A 立項。

