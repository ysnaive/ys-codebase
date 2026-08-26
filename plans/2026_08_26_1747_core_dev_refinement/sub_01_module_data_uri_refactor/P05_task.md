# 實作任務清單 (Task Breakdown)

> 功能名稱：模組資料管理相關 URI 協議釐清與遷移 (Module Data Management URI Protocol Alignment & Migration)  
> 建立日期：2026-08-26  
> 所屬主計畫：[core 與 dev 模組功能打磨 (2026_08_26_1747_core_dev_refinement)](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01 (基礎解算引擎)**：重構 `source/core/core/uri.py`（方案 B、`@/` 自省展開、`UndefinedModuleContextError`、廢除 temp/root）與 `source/core/manifest.json`。
- [x] **TASK-02 (微內核狀態與生命週期)**：重構 `source/core/core/engine.py`（互斥鎖遷移至 cache、消除 hardcoded storage、落實 `--purge`）、`installer.py` 與 `cli.py`。
- [x] **TASK-03 (開發工具鏈與測試沙盒)**：重構 `source/dev/manifest.json`、`source/dev/dev/testing/sandbox.py`、`case.py` 與 `dev/dev/` 工具鏈（消除 `*.root` 與 `temp`）。
- [x] **TASK-04 (工作流資產與發布修復)**：修復 `source/agents-workflow/agents_workflow/publisher.py` 中的 `release_manifest.json` 路徑至 `storage://@/`，重構 `compiler.py` 快取路徑與模板協議。
- [x] **TASK-05 (物理空間清理與歷史遷移)**：物理刪除歷史誤建的 `yscb://storage/core/agents-workflow/` 與 `yscb://.temp/` 目錄。
- [x] **TASK-06 (測試套件升級與全量驗證)**：更新全模組測試套件斷言，實機執行全量回歸測試 (`python yscb.py dev test --all`) 達成 100% Passed。

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01** | Minor | `core.uri` 增加 `uri.move(src, dst)` 輔助方法與 `get_execution_context` 別名 | 增強 VFS API 完整度與向下相容性，已加入單元測試 |
| **TASK-01** | Minor | `ContributesAggregator.scan_and_inject` 補齊 `clean: bool = True` 選擇性參數 | 避免微內核生命週期呼叫時之 TypeError |
| **TASK-02** | Minor | `act_broadcast_event` 在 hook 回傳 None 時標記為 `"success"` | 與通用 Hook 無回傳值之慣用法對齊，避免例外中斷 |
| **TASK-03** | Minor | 依開發者指示將 dev 模組測試沙盒路徑調整為 `cache://dev/sandbox/{sandbox_id}` (`.cache/dev/sandbox/`) | 強化方案 B 模組空間隔離，實機回歸 110/110 通過並清理舊目錄 |
| **TASK-06** | Minor | 回撤開發過程中誤觸發之 `chore(release)` commit 與版本號更動 | 嚴格遵守實作階段禁令，執行 `git reset --mixed` 回復純淨未 release 狀態 |
