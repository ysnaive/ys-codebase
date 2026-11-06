# 實作任務清單 (Task Breakdown)

> 功能名稱：跨模組路徑洩漏根治、背景執行緒 URI 上下文固化與 VFS 原子寫入收口  
> 建立日期：2026-11-06  
> 所屬主計畫：N/A  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：於 `ys_codebase/source/server/server/worker.py` (`WarmWorker.__init__`) 預先解析並固化 `YSCB_ROOT_DIR` 與 `YSCB_HOST_DIR` (`GUARD_ENV_HOST`) 環境變數，並擴充 `test_server.py` 測試
- [x] **TASK-02**：重構 `ys_codebase/source/file-space/file_space/{manager,service,scanner}.py`，全面改用 `core.uri` / `core.vfs` 與 `uri.resolve_yscb_root()` 退避，消除 `project_root / ".cache"` 洩漏並更新 `test_fingerprint_scanner.py`
- [x] **TASK-03**：重構 `ys_codebase/source/ast/ast_engine/{bundler,engine}.py`，改用 `uri.resolve_yscb_root()` 退避與 `core.vfs.write_json`，並於 `test_ast_engine.py` 擴充防洩漏測試
- [x] **TASK-04**：重構 `ys_codebase/source/knowledge-db/knowledge_db/{pipeline,config,service}.py`，改用 `uri.resolve_yscb_root()` 退避與 `core.vfs` 讀寫 `.kdb_worker_state.json`
- [x] **TASK-05**：重構 `ys_codebase/source/agents-workflow/agents_workflow/{compiler,publisher,roadmap}.py` 與 `plans/{verifier,_verifier_healer,session_trace}.py`，統一委派 `core.vfs.write_text` 並消除 `Path.cwd() / ".cache"` 與 `"ys_codebase/..."` 硬編碼
- [x] **TASK-DOC**：同步更新 `docs/file-space/{ARCHITECTURE,DESIGN_NOTES}.md` 與 `docs/server/hot_reload_and_services.md`，完成 `dev check`、`dev test -q` 與 `@build` 熱部署

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差 | - |
