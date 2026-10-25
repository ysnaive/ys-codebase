# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_01_python_aci_toolchain  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Confirmed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-08 在 API 規格書中有對應介面
- [x] **邊界防護**：EC-01 ~ EC-06 有具體錯誤處理策略
- [x] **依賴純淨**：符合 NFR-01（100% Python 標準庫）與 NFR-02（向後相容）指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/agents-workflow/README.md` | Modify | 更新 §6 CLI 快速使用指南中 `plan status [--resume]` 與 `plan verify [--phase] [--log]` 指令說明 |
| **專題手冊** | `docs/agents-workflow/user_guide.md` | Modify | 更新 §1.1 狀態領航與 `--resume` 閱後即焚、§1.4 階段左移檢核、`P01<->P06` 追溯差集與 `--log` 免讀盲寫管線 |
| **設計決策** | `docs/agents-workflow/DESIGN_NOTES.md` | Modify | 新增 `[DN-AW-10]` 記錄 ACI 四步執行管線時序、伴隨檔模型防回溯與 `P01` 刪除線預過濾設計 |
| **微觀註解** | 源碼檔案 Docstrings (`status.py`, `scanner.py`, `verifier.py`, `cli.py`) | Modify | 同步更新新增與擴充公開方法之完整 Type Hints 與標準 Docstring |
| **發布日誌** | CHANGELOG.md | Modify | 於 Phase 7 結案時記錄 `sub_01_python_aci_toolchain` 變更摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> [?] **尖銳問題 1**：當 Agent 執行 `plan verify <plan> --phase P02 --log "完成 P02"` 時，若自動從模板生成的 `P06_test_plan.md (Draft)` 保留了模板預設的 `[功能名稱]`、`[YYYY-MM-DD]` 或缺少 `FT-XX` ID，是否會在緊接著的 Step 3 雙檔合規檢核中自己觸發 `PLACEHOLDER` 或 `ID_MATRIX` `FAIL`？  
> [*] **防護解法**：在 `PlanVerifier._auto_heal_companions` 生成 `P06_test_plan.md (Draft)` 與 `changelog.md` 時，不使用原始未替換模板直接落盤，而是動態填入目標計畫名稱、今日日期 `YYYY-MM-DD`、所屬主計畫名稱（若為 `sub_XX` 則填入父目錄名稱，否則填 `N/A`）、標頭狀態（`P06` 填 `Draft`，`changelog` 填 `In Progress`）、防回溯模型名稱（優先取 `--model`，次取同階段主體檔 `P02` 標頭模型，否則填 `Unknown`），並於 `P06` 預填首筆草案列 `| **FT-01** | 單元測試 | 待於 Phase 4 定稿補齊 | FR-01 | Pending |`，確保生成的伴隨檔 100% 通過 `PLACEHOLDER`、`HEADER`、`TEMPLATE` 與 `ID_MATRIX` 檢核（`[P04:DR-01]`）。

> [?] **尖銳問題 2**：在 `P01` 需求規格書中，表格或文字可能包含刪除線（如 `| ~~**FR-09**~~ | ~~已取消需求~~ |` 或 `~~FR-09~~`），若僅用簡單正則 `r"\b(FR|EC|NFR)-\d+\b"` 提取，是否會把已取消的需求當成孤兒需求而阻斷 `P04/P06` 檢核？  
> [*] **防護解法**：`extract_requirement_ids` 嚴格先剝除 Fenced Code Blocks (`` ```[\s\S]*?``` ``)、HTML 註解 (`<!--[\s\S]*?-->`) 與 Markdown 刪除線 (`~~.*?~~`)，並忽略模板範例佔位符（如 `FR-XX`, `FR-xx`），僅提取含有明確數字編號之有效需求 ID（`r"\b(?:FR|EC|NFR)-\d+\b"`）。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

1. **TASK-01**：擴充 `agents_workflow/plans/status.py`（新增 `get_doc_header_model` 與 `resolve_next_action` 確定性狀態領航推導，支援 `Umbrella` 自動鑽取活躍 `sub_XX`）。
2. **TASK-02**：擴充 `agents_workflow/plans/scanner.py`（新增 `resolve_target_plan_dir` 與 `execute_resume`，實作 `--resume` 原子讀取並 `os.unlink` 刪除 `handoff.md` 及多活躍計畫防呆）。
3. **TASK-03**：擴充 `agents_workflow/plans/verifier.py`（實作 `--phase` 局部檢核、四步執行管線、伴隨檔 `changelog.md` 與 `P06 Draft` 自動補齊、`P02/P04` 雙檔協同檢核、`P01<->P06` 追溯差集比對、自癒型 Actionable Fix Hints 與 `--log` 冪等盲寫追加）。
4. **TASK-04**：更新 `contributes/core.json` 與 `scripts/cli.py`（對齊 `plan status` 與 `plan verify/check` 新增參數與選項，確保 1:1 對稱性）。
5. **TASK-05**：更新 `assets/skills/` 下之 `continue/SKILL.md`、`yscb-cli-guide/SKILL.md`、`development-sop/SKILL.md` 及 `phase_02`/`phase_04`/`phase_07` 參考手冊。
6. **TASK-06**：編寫 `tests/test_plans_aci_toolchain.py` 涵蓋 `FT-01` ~ `FT-08` 與 `ET-01` ~ `ET-06` 測試案例並執行沙盒驗證。
7. **TASK-DOC**：同步更新 `docs/agents-workflow/README.md`、`user_guide.md` 與 `DESIGN_NOTES.md`（新增 `[DN-AW-10]`）。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 伴隨檔 `P06_test_plan.md (Draft)` 與 `changelog.md` 零佔位符物化規範**：自動生成伴隨檔時，Python 動態替換全部標頭佔位符（名稱、今日日期、所屬主計畫、狀態、防回溯模型）並填入合法初始表格列，確保自癒生成之檔案立即符合 `PlanVerifier` 全項檢核標準。
- **[P04:DR-02] `--phase` 對 Umbrella 子計畫與主計畫之解析規則**：當目標路徑指向具體的 `sub_XX` 子目錄（或單一 Full Track 計畫目錄）時，`--phase P02` 僅檢核該目錄下之 `P02` 與伴隨檔；當未指定 `--phase`（預設 `all`）時，維持全目錄與遞迴子目錄完整檢核，100% 向下相容。

