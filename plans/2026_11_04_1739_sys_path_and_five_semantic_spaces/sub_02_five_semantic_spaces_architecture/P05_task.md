# 實作任務清單 (Task Breakdown)

> 功能名稱：sub_02_five_semantic_spaces_architecture  
> 建立日期：2026-11-04  
> 所屬主計畫：2026_11_04_1739_sys_path_and_five_semantic_spaces  
> 狀態：Completed  
> 模型：Unknown  

> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `core.uri`、`contributes/core.json`、`gitignore.py` 與 `installer.py` 之 `config.local://` / `storage.local://` 協議註冊、`.gitignore` 規則與 `cmd_restore` 升級遷移觸發
- [x] **TASK-02**：實作 `core.config` 雙軌物理純淨分離、`dispatcher._read_server_spawn_config` 對齊，以及 `core` `1.2.7.0` (`scripts/migrations/1.2.7.x.py`) 舊版 `config.local.json` 遷移腳本
- [x] **TASK-03**：實作 `core.engine` 模板部署 (`config.local://`)、`act_snapshot` / `act_restore_snapshot`（含 `config.local://`、排除 `storage.local://`）、`act_delete(purge=True)` 四空間清除與多段式 `act_migrate` 升級
- [x] **TASK-04**：實作 `vscode-support` (`schema_compiler.py`, `projector.py`) 與 `dev` (`sandbox.py`) 對五大語意空間之對齊
- [x] **TASK-05**：更新與擴充 `core/tests/` 及 `vscode-support/tests/` 單元測試，並完成 `@build` 熱部署與工作區同步
- [x] **TASK-DOC**：同步更新 `docs/_project/STANDARDS.md`、`docs/core/README.md`、`docs/core/lifecycle_and_hooks.md`、`docs/core/DESIGN_NOTES.md` 與源碼 Docstrings

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| - | - | 無偏差（注意：`ConfigManager.list_modules` 內部使用 `mods_set: Set[str] = {m for m in ()}` 避免類別作用域之 `set = ...` 遮蔽內建 `set()`） | 已於 `core/config.py:L266` 實作並通過 `TestConfigManager` 全部測試 |
