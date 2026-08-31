- **知識庫定向檢索指引**：在啟動 Phase 0 需求發想或架構釐清前，優先依決策樹執行 `python __${yscb.host://yscb.py}__ knowledge-db search <關鍵字> -s` 檢索既有符號、Docstring 與代碼切片；涉及 Public API 變更或重構評估時，調用 `knowledge-db callers` 與 `impact` 評估擴散半徑，避免盲目翻找原始碼。

