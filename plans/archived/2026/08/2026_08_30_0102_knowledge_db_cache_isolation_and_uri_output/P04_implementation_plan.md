# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 快取隔離零 Fallback 固化與搜尋輸出 URI 連結格式重構  
> 建立日期：2026-08-30  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-03 在 API 規格書與架構中有 1:1 對應介面與實作。
- [x] **邊界防護**：EC-01 ~ EC-03 具備跨平台斜線正規化、異常拋出與單/跨行標籤處理防禦。
- [x] **依賴純淨**：100% 原生 Python 標準庫，符合 NFR-01 指標約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **維度 1** | `docs/knowledge-db/README.md` | Modify | 更新 CLI `search` 輸出範例，展示 Markdown 檔案連結與 `file:///` 跳轉功能。 |
| **維度 2** | `docs/knowledge-db/retrieval.md` | Modify | 補充 `to_file_uri` 與 IDE 點擊跳轉支援說明。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若在非 Windows 系統 (Linux/macOS) 或跨平台 CI 容器中執行，`to_file_uri` 是否能保持 RFC 8089 標準 3 條斜線格式？  
> 💡 **防護解法**：`to_file_uri` 內部取得 `Path(file_path).resolve()` 後，以 `p.as_posix()` 處理，若未以 `/` 開頭則補齊 `/`，確保組合 `f"file://{posix_path}"` 時固定為 `file:///...`，100% 符合 RFC 8089。
> 
> ❓ **尖銳問題 2**：若既有單元測試在無 mock 環境下直接實例化 `KnowledgeEngine()`，零 Fallback 機制是否會引發既有測試失敗？  
> 💡 **防護解法**：全面檢視 `source/knowledge-db/tests/`，所有需實例化 `KnowledgeEngine` 或 `SpaceManager` 且存取磁碟快取的測試案例，一律透過 `tempfile.TemporaryDirectory()` 顯式注入 `storage_dir`，隔離測試與生產環境。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：重構 `source/knowledge-db/knowledge_db/space.py`，移除 `_get_storage_root()` 本地相對路徑 Fallback，實施零 Fallback 異常拋出。
- [ ] **TASK-02**：於 `source/knowledge-db/knowledge_db/engine.py` 實作 `to_file_uri()` 與 `format_file_link()` 方法。
- [ ] **TASK-03**：重構 `source/knowledge-db/scripts/cli.py` 中 `search` 簡易模式、詳細模式、預覽模式與 JSON 模式，全面輸出 Markdown 連結。
- [ ] **TASK-04**：更新並擴充 `test_space.py`、`test_engine.py` 與 `test_cli.py` 單元測試套件。
- [ ] **TASK-05**：實機執行 `python yscb.py dev test knowledge-db` 與全量跑測，確認 100% Passed。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]**：確認 P01~P03 與 P06 測試計畫無爭議，剛性定稿並進入 Phase 5 依序實作。
