# 修訂紀錄書 (Revision Log)

> 功能名稱：`core.contributes` 格式驅動合併策略與 `file-space` 來源追蹤修正  
> 建立日期：2026-11-02  
> 所屬主計畫：[2026_11_02_0339_module_space_feasibility_research](../umbrella_overview.md)  
> 狀態：Completed  
> 模型：Gemini 4 Argon (Low)  

> 模板版本：v1.0  

---

## 1. 修訂紀錄清單 (Revision Entries)

### [REV-01] 空間來源訊息顯示改為 `origin(A)` 與 `merged(A, B, ...)` 格式
- **修訂類別**：UI/UX/DX
- **涉及檔案**：
  - `ys_codebase/source/file-space/file_space/schema.py`
  - `ys_codebase/source/file-space/scripts/cli.py`
  - `ys_codebase/source/file-space/file_space/providers.py`
  - `ys_codebase/source/knowledge-db/knowledge_db/providers.py`
  - `ys_codebase/source/file-space/tests/test_file_space_manager.py`
- **修訂摘要**：於 `FileSpaceConfig` 新增 `origin_display` 屬性，當空間為單一來源時顯示 `origin(<provider>)`（如 `origin(agents-workflow)`、`origin(project)`），當多來源合併時顯示 `merged(<provider_a>, <provider_b>, ...)`（如 `merged(agents-workflow, project)`），並同步套用於 `file-space status` CLI 輸出與 `file-space` / `knowledge-db` 動態文檔 Token Provider。
- **驗證結果**：`file-space` 測試套件 `12/12 (100.0%)` 通過，完成 `@build` 安裝與實機 `file-space status` 動態驗證。

---

## 2. 結案與合規檢核 (Completion & Compliance Checklist)

- [x] **修訂與驗證完畢**：所有修訂項目均已實作並通過測試或驗證，無殘留死代碼或除錯資訊。
- [x] **日誌與文檔同步**：已同步更新計畫內 `changelog.md` 與相關 `docs/` 知識庫文檔；若包含使用者可感知之重要變更，依比例原則追加至專案根目錄 `CHANGELOG.md`。
- [x] **標頭狀態更新**：完成上述檢核並將本清單其餘項勾選 `[x]` 後，將頂部標頭 `> 狀態：` 更新為 `Completed`。
- [x] **結構合規檢核（最終守門）**：最後實機執行 `python yscb.py agents-workflow plan verify <plan_name>` 驗證 100% Passed（若檢出未通過項則原地修正重驗）。

