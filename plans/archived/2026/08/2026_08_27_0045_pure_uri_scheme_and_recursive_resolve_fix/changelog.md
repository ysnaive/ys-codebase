# 開發計畫微觀變更紀錄 (Plan Changelog)

> 計畫名稱：純淨語意 URI 協議與遞迴解算缺陷修復 (Pure Semantic URI Protocol & Recursive Resolution Fix)  
> 計畫目錄：`plans/2026_08_27_0045_pure_uri_scheme_and_recursive_resolve_fix/`  
> 建立日期：2026-08-27  
> 當前狀態：Completed  
> 分流層級：Level 0 Fast Track  

---

## 變更日誌流水線 (Changelog Pipeline)

| 時間戳記 | 類型 | 變更內容摘要 | 決策/關聯 |
| :--- | :---: | :--- | :--- |
| 2026-08-27 00:36 | `DISCUSS` | 開發者提出疑問：`ContextInit.md` 中動態語意解析池顯示 `[!UNDEFINED]`，但 `config.project.json` 確有配置。 | 根因排查 |
| 2026-08-27 00:38 | `ANALYSIS` | 完成根因診斷：(1) `core.uri.resolve` 遞迴解算誤用未定義變數 `mod` 拋出 `NameError`；(2) `providers.py` 與 `ContextInit.md` 協議名稱未帶 `workflow.` 前綴。 | 提出修復方案 |
| 2026-08-27 00:40 | `PHASE` | 接收開發者明確指示：清空 `_DEPRECATED_SCHEME_REDIRECTS` 維持純淨版本，不調用 `dev release`，優先修復邏輯。 | `[P00:DR-01]~[DR-04]` |
| 2026-08-27 00:41 | `PHASE` | 剛性伴隨建立 `P00_semantic_requirements.md` 與 `changelog.md`，確認分流為 Level 0 Fast Track。 | Phase 0 ➔ FT-1 |
| 2026-08-27 00:42 | `CODE` | 修復 `source/core/core/uri.py`：清空 `_DEPRECATED_SCHEME_REDIRECTS = {}`，修正第 527 行 `current_module=active_mod`。 | TASK-01 |
| 2026-08-27 00:42 | `CODE` | 修復 `source/core/tests/test_uri.py`：更新 `test_deprecated_scheme_redirection_warning` 斷言未知/舊版協議直接引發 `ValueError`。 | TASK-02 |
| 2026-08-27 00:42 | `CODE` | 修復 `source/agents-workflow/agents_workflow/providers.py`：`primary_schemes` 更新為 `workflow.*` 正規命名清單。 | TASK-03 |
| 2026-08-27 00:42 | `CODE` | 修復 `source/agents-workflow/assets/workflows/ContextInit.md`：更新語意參照標籤為 `workflow.docs://...`。 | TASK-04 |
| 2026-08-27 00:43 | `TEST` | 實機執行 `python yscb.py dev test core`：66/66 Passed (100%)。 | FT-01, ET-01 |
| 2026-08-27 00:43 | `TEST` | 實機執行 `python yscb.py dev test agents-workflow`：22/22 Passed (100%)。 | FT-02, RT-01 |
| 2026-08-27 00:45 | `DOC` | 產出 `fast_track_plan.md`，完整記錄需求、決策、任務清單、實機測試日誌與結案摘要。 | FT-3 結案 |
| 2026-08-27 00:46 | `BUILD` | 執行 `python yscb.py dev build --all`，產出 `core@1.0.0.build`、`agents-workflow@1.0.0.build`、`dev@1.0.0.build`。 | 本地建置產物 |
| 2026-08-27 00:47 | `INSTALL` | 執行 `python yscb.py install <mod>@build --provider=./ys_codebase/build --force`，將 modules 切換為 build 版本並發布驗證成功。 | 測試環境部署 |
| 2026-08-27 00:50 | `CODE` | 接收使用者指示，修改 `source/agents-workflow/scripts/hook.core.py`：在 `on_reload` 事件時自動調用 `ReleasePublisher().release_all()`。 | TASK-05, `[P00:DR-05]` |
| 2026-08-27 00:50 | `TEST` | 於 `test_compiler.py` 追加 `test_ft_11_on_reload_hook_triggers_release_all`，實測 23/23 通過。 | FT-03 |
| 2026-08-27 00:51 | `VERIFY` | 重新 `dev build agents-workflow` 並安裝，實機執行 `python yscb.py reload` 驗證自動觸發 release 成功。 | 驗證通過 |
