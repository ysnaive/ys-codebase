# 實作任務清單 (Task Breakdown)

> 功能名稱：modules_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Completed  
> 模板版本：v1.0  

---

## 1. 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：更新 `yscb.py` 內部 Git 忽略生成器 `_generate_internal_gitignore`，注入 `/.modules/` 條目，並實作標記區塊軟合併以因應 `"yscb://" == "project://"` 拓撲 (FR-01)
- [x] **TASK-02**：全面切換 `yscb.py` 運行端路徑組裝至 `.modules`（`cmd_init`、`dispatch_module`、`_get_installed_module_commands`）(FR-02)
- [x] **TASK-03**：實作 `yscb.py` 四階模組提取函式 `_restore_module_package` 與原生 `cmd_restore`，支援 `@build` 與 `file://` Provider (FR-03)
- [x] **TASK-04**：實作 `yscb.py` 極速 JIT 模組同步守門 `_is_modules_dirty` 與 `_ensure_jit_modules_sync` (FR-04)
- [x] **TASK-05**：更新 `source/core/contributes/core.json` 與 `source/core/core/uri.py` 空間協議預設值為 `yscb://.modules/` (FR-02)
- [x] **TASK-06**：編寫單元測試套件 `source/core/tests/test_restore_and_jit_modules.py` (FT-01~FT-05, ET-01~ET-02, PT-01)
- [x] **TASK-07**：同步修訂最高工程規範 `docs/_project/STANDARDS.md`、`docs/core/README.md` 與 `source/core/README.md` (FR-05)
- [x] **TASK-08**：Dogfooding 閉環驗證與全生態系回歸跑測 (RT-01, NFR-03) (298/298 通過)

---

## 2. 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01** | `Minor` | 依據使用者補充指示，因應 `"yscb://" == "project://"` 拓撲，`_generate_internal_gitignore` 嚴格禁止全量覆寫，升級為標記區塊軟合併 (Soft Merge)。 | 於 `yscb.py` 引入 `INTERNAL_IGNORE_BEGIN` 與 `INTERNAL_IGNORE_END` 標記區塊與歷史規則正則替換，相容既有自訂與其他模組規則。記錄於 `[P00:DR-07]`。 |
| **TASK-03** | `Minor` | 在模組提取還原邏輯中，針對 `@build` 開發版與存在比 mirror 更晚修改之 build 產物，優先採納 build 包並自動同步鏡像庫，同時完整支援 `file://` 本地檔案 URL 解碼。 | 於 `yscb.py` 增強 `_fetch_and_extract_zip` 與 `_restore_module_package` 之路徑歸一化與優先序判定。 |
