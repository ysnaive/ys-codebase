# 程式碼實作任務追蹤 (Implementation Tasks)

> 功能名稱：架構合規性缺陷修復與穩固性強化 (Architecture Compliance Bugfix & Hardening)  
> 建立日期：2026-08-25  
> 所屬主計畫：[2026_08_23_2030_architecture_refactor](../umbrella_overview.md)  
> 依據 P04：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 狀態：Completed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.4  

---

## 1. 任務執行進度表 (Task Checklist)

- [x] **TASK-01**：`core.uri` 定錨與 Context 注入重構
  - [x] 實作 `_get_yscb_root()` 以 `__file__` 往上 3 層常數自定位
  - [x] 實作 `set_host_dir()` 與 `get_host_dir()`（優先內部變數，次之 `YSCB_HOST_DIR`）
  - [x] 移除 `_find_host_config` 中的 `while` 爬目錄與 `os.getcwd()` fallback 猜測，組態缺失時拋出 `FileNotFoundError`
  - [x] 更新 `resolve()` 與 `to_uri()` 對接 `_get_yscb_root()`
- [x] **TASK-02**：`core.engine` 宿主組態解耦與相依拓撲求解
  - [x] `_get_config()` 與 `_save_config()` 改用 `host_dir` 實體路徑操作 `yscb.config.json`
  - [x] `act_init()`、`act_snapshot()`、`act_restore_snapshot()` 移除 `project://` 依賴
  - [x] 實作 `_parse_dependencies()` 雙向支援 Dict 與 List
  - [x] 實作 `act_solve_deps()` 遞迴相依拓撲求解與循環相依檢測
- [x] **TASK-03**：`core.installer` 反向相依安全阻斷防護
  - [x] `cmd_remove()` 實作反向依賴掃描
  - [x] 被依賴模組未帶 `--force` 時輸出 Error 並 Exit 1；帶 `--force` 輸出 Warning 放行
  - [x] 更新 `cli.py` 支援 `--force` 參數解析
- [x] **TASK-04**：`dev.builder` `index.json` 自動生成與維護
  - [x] 實作 `_update_index_json()` 增量維護 `build/{module}/index.json`
  - [x] `build_module()` 打包完成後觸發索引更新
- [x] **TASK-05**：`yscb.py` 宿主注入 `YSCB_HOST_DIR` 與 `cmd_init` 補齊
  - [x] `cmd_init()` 寫入初始組態時補齊 `"default_provider": provider_arg`
  - [x] `dispatch_module()` 在派發子程序時注入 `os.environ["YSCB_HOST_DIR"]`
- [x] **TASK-06**：補齊說明書、測試套件與全量回歸驗證
  - [x] 建立 `source/dev/contributes.format.md`
  - [x] 於 `source/core/tests/` 與 `source/dev/tests/` 建立 FT-01~08 與隔離測試案例
  - [x] 執行 `dev test --all --verbose` 達到 38/38 (100%) Passed

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏差說明 | 處置方式 | 影響範圍 |
| :--- | :---: | :--- | :--- | :--- |
| - | - | 無結構性偏差，所有實作嚴格對齊 P01~P04 規劃 | - | - |
