# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_01_python_aci_toolchain  
> 建立日期：2026-10-23  
> 所屬主計畫：2026_10_23_1314_agents_workflow_aci_and_delegation_evolution  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：擴充 `agents_workflow/plans/status.py`（新增 `get_doc_header_model` 與 `resolve_next_action` 確定性狀態領航推導，支援 `Umbrella` 自動鑽取活躍 `sub_XX`）
- [x] **TASK-02**：擴充 `agents_workflow/plans/scanner.py`（新增 `resolve_target_plan_dir` 與 `execute_resume`，實作 `--resume` 原子讀取並 `os.unlink` 刪除 `handoff.md` 及多活躍計畫防呆）
- [x] **TASK-03**：擴充 `agents_workflow/plans/verifier.py`（實作 `--phase` 局部檢核、四步執行管線、伴隨檔 `changelog.md` 與 `P06 Draft` 自動補齊、`P02/P04` 雙檔協同檢核、`P01<->P06` 追溯差集比對、自癒型 Actionable Fix Hints 與 `--log` 冪等盲寫追加）
- [x] **TASK-04**：更新 `contributes/core.json` 與 `scripts/cli.py`（對齊 `plan status` 與 `plan verify/check` 新增參數與選項，確保 1:1 對稱性）
- [x] **TASK-05**：更新 `assets/skills/` 下之 `continue/SKILL.md`、`yscb-cli-guide/SKILL.md`、`development-sop/SKILL.md` 及 `phase_02`/`phase_04`/`phase_07` 參考手冊
- [x] **TASK-06**：編寫 `tests/test_plans_aci_toolchain.py` 涵蓋 `FT-01` ~ `FT-08` 與 `ET-01` ~ `ET-06` 測試案例並執行沙盒驗證
- [x] **TASK-DOC**：同步更新 `docs/agents-workflow/README.md`、`user_guide.md` 與 `DESIGN_NOTES.md`（新增 `[DN-AW-10]`）

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-04** | Minor | `contributes/core.json` 中 `options` 外層鍵名在 `core.commands` 代表互斥群組 (Mutual Exclusion Group)，因此將 `--phase`、`--log`、`--type`、`--model` 分別置於獨立群組鍵 (`phase_opt`, `log_opt`, `log_type_opt`, `model_opt`) 以支援同時組合傳參 | 已修正並驗證通過 |

