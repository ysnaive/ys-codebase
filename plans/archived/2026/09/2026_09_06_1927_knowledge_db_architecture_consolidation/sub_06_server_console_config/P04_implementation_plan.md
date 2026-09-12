# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：server_console_config  
> 建立日期：2026-09-06  
> 所屬主計畫：2026_09_06_1927_knowledge_db_architecture_consolidation  
> 狀態：Confirmed  

> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 均在 P03 API 規格書中定義具體類別與函式簽名
- [x] **邊界防護**：EC-01 (互斥解析)、EC-02 (寬鬆防禦型別轉型)、EC-03 (已運行探測) 均已設計對應策略
- [x] **依賴純淨**：NFR-01 零外部依賴、NFR-02 配置熱自癒約束完全滿足

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `source/server/contributes.format.md` | Modify | 更新 `server start` 說明，明確標示 `--console` 為除錯附加參數 |
| **設計決策** | `docs/server/DESIGN_NOTES.md` | Modify | 登錄 `[DN-04]`：Server 模組組態化與 Console 模式分流決策 |
| **發布日誌** | `plans/.../sub_06_.../changelog.md` | Modify | 完整記錄 Phase 0~7 推進細節 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若開發者在組態檔中配置了非布林型別（如 `"true"`、`"yes"`、`1` 或甚至物件/陣列），是否會造成執行階段例外或邏輯倒錯？  
> 💡 **防護解法**：在 `ServerConfig.load` 內建防禦轉型函式 `_parse_bool()`，布林值直接回傳，字串轉小寫比對 `{"true", "1", "yes", "on"}`，其餘非法型別一律安全回退預設值 `False`。

> ❓ **尖銳問題 2**：若使用者在 CLI 同時傳入 `python yscb.py server start --console --daemon`，會發生什麼情況？  
> 💡 **防護解法**：在 `argparse` 中使用 `add_mutually_exclusive_group()`，CLI 在解析階段即直接輸出 `error: argument --daemon: not allowed with argument --console` 並返回非零狀態碼，杜絕行為歧義。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：新增 `source/server/server/config.py`，實作 `ServerConfig` 資料類別與 `core.config` 對接 (FR-01, EC-02)
- [ ] **TASK-02**：修改 `source/server/scripts/cli.py`，重構 `_handle_start` 參數解析與互斥群組，新增 `_resolve_enable_console` (FR-02, FR-03, EC-01)
- [ ] **TASK-03**：新增 `source/server/tests/test_server_config.py`，編寫 FT-01 ~ FT-05 單元測試 (FT-01~05)
- [ ] **TASK-04**：執行 `server` 單元測試與靜態合規性檢驗 (FT-06, FT-07)
- [ ] **TASK-05**：文檔同步交付 (`docs/server/DESIGN_NOTES.md`, `source/server/contributes.format.md`)

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 組態載入器 100% 整合 `core.config.get`，直接享有雙層合併與 `mtime` 快取自癒機制，不重複造輪子。
