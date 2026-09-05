# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：sub_03_networkx_call_graph_and_impact_analysis  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P03：[P03_api_spec.md](./P03_api_spec.md)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：
  - `FR-01` (NetworkX DiGraph 儲存) ➔ `CallGraphIndex` 內部採用 `nx.DiGraph`
  - `FR-02` (多語言拓撲協議) ➔ `LanguageTopologyProtocol` 抽象定義與註冊機制
  - `FR-03` (FQN 作用域消歧杜絕幽靈關聯) ➔ `TopologyLinker.resolve_call_site` 四階精確過濾
  - `FR-04` (全方位符號選擇器) ➔ `SymbolSelector.parse` 與 `ParsedSelector.matches`
  - `FR-05` (高精度多階影響面分析) ➔ `CallGraphIndex.query_impact`
  - `FR-06` (門面與 CLI 契約相容) ➔ 維持 `add_edge`, `get_callers`, `get_callees`, `query_impact` 等簽名
- [x] **邊界防護**：
  - `EC-01` (循環依賴) ➔ NetworkX 前驅走訪 visited 防護剪枝
  - `EC-02` (語法無效) ➔ 回退為純識別符文字比對，不拋出例外
  - `EC-03` (無法解析) ➔ 標記為未鏈接邊，杜絕全域誤連
  - `EC-04` (孤立節點) ➔ 空安全回傳結構
  - `EC-05` (快取損毀) ➔ JIT 差量自癒重構
- [x] **依賴純淨**：符合純 Python、秒級微環境適配要求 (`networkx >= 3.0`)

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **專題手冊** | `docs/knowledge-db/call_graph_and_reference_index.md` | Modify | 更新為 NetworkX 圖架構、符號選擇器微型語法與多語言協議說明。 |
| **模組手冊** | `source/knowledge-db/README.md` | Modify | 增補 CLI 符號選擇器用法範例（`class Foo`, `struct Point.x`, `foo.bar()`）。 |
| **設計決策** | `docs/knowledge-db/DESIGN_NOTES.md` | Modify | 登記 `[DN-KDB-04]` (NetworkX 圖模型與 FQN 幽靈關聯消除機制)。 |
| **發布日誌** | `CHANGELOG.md` | Modify | 結案時記錄 sub_03 高階成果。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當專案極度龐大（例如 10 萬個節點、50 萬條邊）時，NetworkX 是否會導致記憶體暴增？  
> 💡 **防護解法**：`networkx.DiGraph` 的節點僅儲存字串 `symbol_id` 與精簡元數據，邊屬性僅在有調用點時才掛載輕量 `SymbolCallSite` 參照。10 萬節點約消耗 40~60MB 記憶體，完全處於現代微環境輕量預算內。
>
> ❓ **尖銳問題 2**：若使用者輸入不合法語法如 `class Foo...bar()()()`，系統是否會 Crash？  
> 💡 **防護解法**：`SymbolSelector` 實作防禦式正規化解析，任何非標準前綴或多重括號均採嚴格修剪並安全回退，確保 API 與 CLI 零崩潰。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `manifest.json` 宣告 `networkx: ">=3.0"` 依賴，驗證微環境相容性。
- [ ] **TASK-02**：實作 `knowledge_db/selector.py`，支援全方位符號選擇器微型語法與比對。
- [ ] **TASK-03**：實作 `knowledge_db/protocol.py`，定義多語言調用拓撲協議與適配架構。
- [ ] **TASK-04**：重構 `knowledge_db/graph.py`，以 `networkx.DiGraph` 實現圖儲存、持久化與高精度 `query_impact`。
- [ ] **TASK-05**：重構 `knowledge_db/linker.py`，導入 FQN 與階層作用域消歧，徹底杜絕跨檔案幽靈關聯。
- [ ] **TASK-06**：擴充 `scripts/cli.py` 支援選擇器語法，編寫 `test_selector.py` 與 `test_networkx_graph.py` 並回歸測試。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全方位符號選擇器語意標準化**：確立 `[<kind>\s+][<scope>.]<name>[()]` 語法，與 CLI 各指令全面貫通。
- **[P04:DR-02] NetworkX 內部持久化格式相容**：維持 `to_dict` / `from_dict` 字典格式與 Gzip Pickle Protocol 5 二進位快取，確保向後相容。
