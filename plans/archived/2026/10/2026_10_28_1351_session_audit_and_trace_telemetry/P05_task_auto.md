# 實作任務清單 (Task Breakdown)

> 功能名稱：Session 隱形摩擦自檢技能與三級軌跡提取機制 (`session_audit_and_trace_telemetry`)  
> 建立日期：2026-10-28  
> 所屬主計畫：獨立計畫 (Standalone)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (`core` 飛行紀錄器與派發攔截)**：建立 `ys_codebase/source/core/core/telemetry.py`，更新 `core/__init__.py` 與 `core/commands/dispatcher.py`，實作 `cache://core/telemetry.jsonl` 寫入、512KB 滾動截斷與讀取 API (`FR-01`, `EC-03`, `EC-04`, `NFR-01`)。
- [x] **TASK-02 (`session-trace` 三級軌跡提取與五大訊號引擎)**：建立 `ys_codebase/source/agents-workflow/agents_workflow/plans/session_trace.py` 並匯出於 `plans/__init__.py` 與 `agents_workflow/__init__.py`，實作多 `release_targets` 尾行信標定錨、Telemetry 時間窗切片、`mtime` 與 `changelog.md` 回寫消歧、五大摩擦訊號偵測與 Tier 3 逆向審訊保底 (`FR-02` ~ `FR-04`, `EC-01`, `EC-02`, `EC-05`)。
- [x] **TASK-03 (CLI 掛載與初版 `/session-audit` 技能導出)**：更新 `agents-workflow/scripts/cli.py`、`contributes/core.json`、`contributes/agents-workflow.json`、`contributes/_manifest.md` 與 `extension-guide.md`，建立初版 `assets/skills/session-audit/SKILL.md` (`FR-05`, `NFR-02`)。
- [x] **TASK-04 (子系統 1:1 單元與邊界測試與 `@build` 部署驗證)**：於 `core/tests/test_cli_router.py`、`core/tests/test_engine.py`、`agents-workflow/tests/test_plans_toolchain.py` 與 `agents-workflow/tests/test_compiler.py` 補齊正負雙向單元測試，通過 `contributes check`、`dev check`、`dev test` 並安裝 `core@build`、`dev@build` 與 `agents-workflow@build` 同步物化 (`FT-01` ~ `FT-05`, `ET-01` ~ `ET-05`)。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01 / TASK-04** | Minor | 實測過程中發現在跨平台虛擬檔案系統下，原子目錄替換可能殘留 `.old_*` / `.staging_*` 暫存目錄，且 Pylance 未排除 `.cache` 沙盒與 `YSCBTestCase` 未還原 `uri._active_host_dir`。經 `/Discuss` 確認採方案 A 擴充 `AtomicEngine` 殘留清理、`.vscode` `python.analysis.exclude` 與 `YSCBTestCase` 狀態還原。 | 已於 `core/engine.py`, `core/ide_projector.py`, `core/vfs/os_backend.py`, `dev/testing/case.py`, `dev/testing/sandbox.py` 實作並通過全量回歸測試。 |

