---
target: "AgentsWorkflow/ExtensionVerifiers"
doc_type: "topic_doc"
status: "active"
source_paths:
  - "source/agents-workflow/scripts/verify_plan.py"
  - "extensions/dogfooding_pipeline_verify.py"
related_docs:
  - "./README.md"
  - "./DETERMINISTIC_SCRIPTS.md"
last_updated: "2026-08-23"
---

# 抽象外掛式 Extension Verifier Hook 規範手冊

本文件說明 `agents-workflow` 中 `verify_plan.py` 如何透過抽象外掛機制，動態調度專案特化守門腳本，達成「通用工作流純淨、專案特化解耦」的設計目標。

---

## 1. 核心設計理念與解耦原則

- **通用驗證純淨性**：`source/agents-workflow/scripts/verify_plan.py` 嚴禁硬編碼任何特定專案的商業或發布邏輯。
- **動態外掛 Hook 協定**：
  - `verify_plan.py` 掃描 Plan 目錄中各 Markdown 文件之 `> 擴充項目：` Header 宣告。
  - 自動於 `sop_ext://`（即 `extensions/` 或 `workflows/extensions/`）尋找 `<extension_name>_verify.py` 或 `<extension_name>.py`。
  - 若存在，以子進程執行：`python <ext_verify_script> <plan_dir>`。
  - 根據 exit code（`0` 為通過，非 `0` 為阻斷）與輸出字串（`[WARN]`, `[ERROR]`）動態注入審查報告。

---

## 2. 專案特化範例：`dogfooding_pipeline_verify.py`

在 `ys-codebase` 工具庫自引用專案中，建立專屬的發布守門外掛：
1. **源碼變更與版本遞進檢核**：若本計畫有源碼變動，校驗對應模組 `manifest.json` 版本是否已正確遞進。
2. **三態版本一致性檢核**：校驗全專案【源碼 == 建置 == 安裝】三態版本是否完全同步（`[SYNCED]`）。
3. **全局發布日誌檢核**：已結案計畫是否已於 `project://CHANGELOG.md` 登記發布摘要。
