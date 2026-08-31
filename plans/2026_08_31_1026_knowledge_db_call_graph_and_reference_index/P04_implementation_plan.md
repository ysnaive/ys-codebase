# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge_db_call_graph_and_reference_index  
> 建立日期：2026-08-31  
> 所屬主計畫：無 (獨立主計畫)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 P03 API 規格書中 100% 具備對應介面契約與資料結構。
- [x] **邊界防護**：EC-01 ~ EC-05 在 `TopologyLinker`、`CallGraphIndex` 與 `ScopeStack` 中均有具體防禦與降級機制。
- [x] **依賴純淨**：100% 採用純 Python 原生標準庫（`ast`, `gzip`, `pickle`, `hashlib`），符合 NFR-01。
- [x] **測試映射**：P06 測試計畫包含 FT-01~07、ET-01~02、PT-01 與 RT-01，1:1 覆蓋所有 FR/EC/NFR。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **模組手冊** | `docs/knowledge-db/README.md` | Modify | 新增 `callers`、`callees`、`impact` CLI 指令範例與說明。 |
| **專題手冊** | `docs/knowledge-db/call_graph_and_reference_index.md` | **New** | 詳細記載雙層拓撲架構、四階消歧演算法、整數池化雙向圖與 RFC 8089 輸出機制。 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 `DN-07: 整數池化雙向調用圖譜與四階消歧鏈接 (Integer Pooled Call Graph & 4-Tier Disambiguation)`。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：若專案中存在深層遞迴調用（如 A 呼叫 B、B 呼叫 C、C 呼叫 A），執行 `impact` 查詢時是否會引發 RecursionError 或死循環？**  
> 💡 **防護解法**：`CallGraphIndex.query_impact` 採用廣度優先走訪 (BFS)，內部維護全域 `visited_set: Set[int]`。任何已訪問過的符號節點一律剪枝跳過，保證圖遍歷時間複雜度為 $O(V + E)$，徹底杜絕無窮遞迴。

> ❓ **尖銳問題 2：若兩個不同模組定義了同名的類別方法（例如 `SpaceManager._get_storage_root` 與 `ConfigManager._get_storage_root`），靜態鏈接如何防止誤判？**  
> 💡 **防護解法**：`TopologyLinker` 嚴格執行四階消歧流水線。Tier 1 優先比對呼叫者同類別；Tier 2 依據檔頭顯式 import（`from space import SpaceManager`）精準鎖定；若均未命中才在同語意空間 (Tier 3) 內根據 context prefix（如 `self.space_manager._get_storage_root`）打分匹配，杜絕跨模組同名干擾。

> ❓ **尖銳問題 3：單一檔案發生變更時，如何確保增量熱自愈不會遺漏舊調用邊或殘留幽靈邊？**  
> 💡 **防護解法**：`CallGraphIndex.patch_incremental` 接收 `dirty_file_paths`，先精準搜集屬於該檔案的舊符號清單，一舉拔除其作為 Caller 的所有出度邊與作為 Callee 的入度邊，再重新注入新解析之 `new_edges`，保證差量修補與全量重構完全等價。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `schema.py` 實作 `SymbolCallSite` 與 `CallGraphNode` 資料結構模型 (FR-01)。
- [ ] **TASK-02**：在 `parsers/base.py` 與 `parsers/python_parser.py` 實作 `CallSiteVisitor`、`ScopeStack` 與調用點/import 提取 (FR-02)。
- [ ] **TASK-03**：新增 `linker.py`，實作 `TopologyLinker` 四階消歧鏈接演算法 (FR-03)。
- [ ] **TASK-04**：新增 `graph.py`，實作 `CallGraphIndex` 雙向圖索引、整數池化、Gzip 二進位快取與 JIT 增量修補 (FR-04, FR-05)。
- [ ] **TASK-05**：在 `engine.py` 整合 `act_callers`、`act_callees`、`act_impact` 與 JIT 變更嗅探流水線 (FR-06)。
- [ ] **TASK-06**：在 `cli.py` 擴充 `callers`、`callees`、`impact` CLI 指令與 RFC 8089 輸出 (FR-06)。
- [ ] **TASK-07**：編寫完整單元測試套件 `tests/test_call_graph.py` 並通過沙盒跑測 (FT-01~07, ET-01~02, PT-01, RT-01)。
- [ ] **TASK-DOC**：同步更新 `docs/knowledge-db/` 模組手冊、專題手冊與 `DESIGN_NOTES.md`。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿**：確認 Phase 1~3 規格與依賴拓撲無環，P06 測試計畫同步定稿為 `Confirmed`，正式進入 Phase 5 編碼實作。
