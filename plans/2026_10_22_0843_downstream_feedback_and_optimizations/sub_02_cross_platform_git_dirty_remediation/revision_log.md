# 修訂紀錄書 (Revision Log)

> 功能名稱：sub_02_cross_platform_git_dirty_remediation  
> 建立日期：2026-10-22  
> 所屬主計畫：2026_10_22_0843_downstream_feedback_and_optimizations  
> 狀態：Completed  
> 模型：Claude Opus 5.5 (Medium)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

> 開發者授權：本修訂階段允許直接修改原始碼（2026-10-22，豁免 Revision 模式「不涉核心邏輯 / Bug Fix」熔斷條件），處理 P07 列出之兩項殘留風險。

### [REV-01] VFS 文字寫入固定 LF 換行
- **修訂類別**：Parameter
- **涉及檔案**：
  - `ys_codebase/source/core/core/vfs/os_backend.py`
  - `ys_codebase/source/core/tests/test_ide_projector_cross_platform.py`
- **修訂摘要**：`OSBackend.write_text`（atomic 與非 atomic）與 `atomic_write` 文字模式改以 `newline="\n"` 開檔，Windows 不再將 `\n` 轉譯為 `\r\n`；內容中顯式 `\r\n` 原樣保留。所有經 VFS 寫出之受追蹤檔（含 `.vscode/settings.json`、`config.project.json`）跨平台位元組一致。原始碼內無需 CRLF 之腳本檔經由 VFS 寫出。
- **驗證結果**：新增 `test_rev01_vfs_write_text_keeps_lf`；`core` 全量測試通過。

### [REV-02] `settings.json` 為 JSONC 時不整檔覆寫
- **修訂類別**：Parameter
- **涉及檔案**：
  - `ys_codebase/source/core/core/ide_projector.py`
  - `ys_codebase/source/core/tests/test_ide_projector_cross_platform.py`
- **修訂摘要**：`sync_vscode_settings` 讀取既有 `settings.json` 解析失敗（如 VS Code 允許之註解 / 尾逗號）或非物件時，改為輸出 stderr 警告並回傳 `False` 略過同步，不再以空字典覆寫整檔（原註解宣稱「安全略過」但實際會覆寫）。取捨：含註解之 `settings.json` 將不會自動注入 `extraPaths`，需使用者自行處理。
- **驗證結果**：新增 `test_rev02_jsonc_settings_not_overwritten`（檔案位元組完全不變）；`core` 全量測試通過。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 `docs/` 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 `CHANGELOG.md`。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。
