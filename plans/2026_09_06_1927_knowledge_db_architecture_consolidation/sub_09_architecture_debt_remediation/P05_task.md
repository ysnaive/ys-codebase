# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_09_architecture_debt_remediation  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：Tier 1 高風險關鍵穩定性修復 (H-01: InterProcessLock 統一替換、H-02: 移除 is_path_watched 寬鬆兜底)
- [x] **TASK-02**：Tier 2 基礎設施下沉與狀態原子化 (M-01: core.platform.venv.ensure_private_venv 下沉與 master/worker 複用、M-02: master._write_state VFS 原子化)
- [x] **TASK-03**：Tier 2 宿主入口優化與安全修復 (M-03: yscb.py _MODULE_CACHE、M-04: _is_modules_dirty FD 洩漏修復)
- [x] **TASK-04**：Tier 2 KnowledgeEngine 進程單例全域共享 (M-05: engine 導出 get_engine、service 與 cli 共享同一實例)
- [x] **TASK-05**：Tier 3 低風險代碼清理、並發保護與契約健全 (L-01: Guard Docstring、L-02: pipeline _CACHE_LOCK、L-03: 動態逾時、L-04: 清理 engine 未用常數、L-05: main 展開、D-01: BaseServiceWorker 契約、D-02: VFS 跨後端防禦)
- [x] **TASK-TEST**：全生態系單元測試與自動化回歸驗證 (Core 142/142, Server 20/20, Knowledge-DB 144/144, Dev 83/83, Agents-Workflow 74/74 全數通過)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
