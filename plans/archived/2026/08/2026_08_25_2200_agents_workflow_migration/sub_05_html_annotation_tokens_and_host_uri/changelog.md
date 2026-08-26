# 計畫變更日誌 (Changelog) - sub_05_html_annotation_tokens_and_host_uri

> 所屬計畫：`sub_05_html_annotation_tokens_and_host_uri`  
> 分流層級：Level 0 (Fast Track)  
> 建立日期：2026-08-26  

---

## 變更紀錄

### FT-1: 需求與架構說明書
- **計畫初始化**：產出 [`FT_plan.md`](./FT_plan.md)（定義 HTML 註解 Token 與 `yscb.host://` 協議規格）。
- **狀態**：`Confirmed`。

### FT-2: 程式碼實作與回歸驗證
- **Token 註冊與 Replace 解算**：於 `source/agents-workflow/manifest.json` 註冊 `BEGIN_HTML_ANNOTATION` 與 `END_HTML_ANNOTATION`，配置 `mode: "replace"` 替換為 `<!--` 與 `-->`。
- **yscb.host 協議支援**：於 `source/core/manifest.json` 宣告 `yscb.host` 協議，並於 `source/core/core/uri.py` 實作 fast-path 與 `{yscb_host}` 變數替換。
- **單元測試與全域回歸**：更新 `test_compiler.py` 與 `test_uri.py`，全系統回歸測試 104/104 案例 100% Passed。
- **狀態**：`Completed`。

### FT-3: 結案審查與 1:1 知識庫交付
- **交付文檔**：更新 `docs/core/URI_SCHEMES.md`、登記 `[DN-14]` 於 `docs/core/DESIGN_NOTES.md`、登記 `[DN-AW-06]` 於 `docs/agents-workflow/DESIGN_NOTES.md`，追加日誌至 `CHANGELOG.md`。
- **狀態**：`Completed`。
