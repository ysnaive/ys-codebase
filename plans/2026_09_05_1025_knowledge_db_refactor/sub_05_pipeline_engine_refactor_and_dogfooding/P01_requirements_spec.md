# 需求規格說明書 (Requirements Specification)

> 功能名稱：sub_05_pipeline_engine_refactor_and_dogfooding  
> 建立日期：2026-09-05  
> 所屬主計畫：2026_09_05_1025_knowledge_db_refactor  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 呈現層格式化器解耦 (`formatter.py`) | 將 `engine.py` 中約 700 行之 CLI/Markdown 呈現邏輯完整抽離至 `ResultFormatter`，包含代碼行高亮、Markdown 超連結標籤生成 (`format_file_link`、`to_file_uri`、`normalize_workspace_path`)、動態切片字元衰減算法 (`compute_dynamic_snippet_lines`) 與 4 大格式化器 (`format_search_output`、`format_callers_output`、`format_callees_output`、`format_impact_output`)。 | P0 | [P00:DR-01] |
| **FR-02** | 索引建置與熱補丁解耦 (`pipeline.py`) | 將多空間倒排索引與向量索引之建置流程 (`build_unified_index`、`build_index`)、指紋掃描比對、增量熱補丁修補 (`_hot_patch_unified_index`) 與 Gzip 二進位快取管理抽離至 `IndexingPipeline` 類。 | P0 | [P00:DR-02] |
| **FR-03** | `KnowledgeEngine` 門面協調與契約保持 | `KnowledgeEngine` 保留為頂層輕量門面 (Facade)，實例化並協調各模組子系統，所有現存公有方法 (`status`, `scan`, `bundle`, `build_unified_index`, `build_index`, `search`, `clean`, `get_call_graph`, `act_callers`, `act_callees`, `act_impact`, `format_*`, `normalize_workspace_path`, `to_file_uri`, `format_file_link`) 100% 保持簽名與型態相容。 | P0 | [P00:DR-03] |
| **FR-04** | 生態系對外 CLI 契約全量驗收 | 實機核驗 `knowledge-db` 各 CLI 命令（`search`、`callers`、`callees`、`impact`、`status`、`bundle`、`clean`）於純文字與 `--json` 輸出模式下之行為與現行契約 100% 一致。 | P0 | [P00:DR-04] |
| **FR-05** | 生態系 Dogfooding 物化與知識庫登記 | 執行 `python yscb.py install knowledge-db@build --force` 完成本地物化更新；以實機檢索自身源碼庫驗證端到端閉環；於 `docs/knowledge-db/DESIGN_NOTES.md` 登記 `[DN-12]` 並同步文檔與全域 `CHANGELOG.md`。 | P0 | [P00:DR-04] |
| **FR-06** | 8,000 字元上限與全域重複資訊極致剔除 (Universal Redundancy Purge) | 將 search CLI 輸出上限調降為 8,000 字元（`AUTO_BUDGET_CHARS = 8000`）；於 `formatter.py` 實作通用切片純化與去重管道 (`UniversalRedundancyFilter`)，徹底剔除任何與已呈現元資料重複之內容（包含：與 Docstring/摘要高度重疊之註解、與 Token/標題重疊之 Markdown `# Heading`、授權版權宣告樣板、連續冗餘空行等），最大幅度提昇 8,000 字元內的可執行真實邏輯資訊密度。 | P0 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 空搜尋結果與特殊字元檢索 | 當檢索無任何符合項目或輸入含正則/Markdown 特殊字元時，格式化器平滑輸出空清單或安全提示，不引發異常中斷。 |
| **EC-02** | 快取損毀或不存在之空間名稱 | 當倒排快取損毀或指定未註冊空間時，`IndexingPipeline` 能攔截 `SpaceNotFoundError` 並觸發安全回退或自動修補重建。 |
| **EC-03** | 符號消歧失敗與非圖譜節點 | 當查詢 callers/callees/impact 之目標符號不在調用圖譜中時，回傳空清單拓撲結構並給出友善找不到提示。 |
| **EC-04** | 動態預算極限字元截斷 (8,000 字元) | 當搜尋結果字元數逼近或超越 `AUTO_BUDGET_CHARS` (8,000 字元) 時，動態切片行數線性平滑降至 0，並強制保留至少 `AUTO_MIN_RENDERED_ITEMS` (5 個) 符號條目。 |
| **EC-05** | 切片去重殘缺防禦 | 若函式僅包含簽名與 Docstring 而無其他本體代碼，去重機制必須保留定義簽名行與安全標註，嚴禁回傳完全空白的切片區塊。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構品質 / 行數約束 | 重構後 `engine.py` 總行數由 1,765 行降至 $\le 450$ 行；解耦出之 `formatter.py` 與 `pipeline.py` 維持單一職責；輸出字元嚴格限制於 8,000 字元自適應預算內。 |
| **NFR-02** | 回歸測試通過率 | 執行 `python yscb.py dev test knowledge-db --quiet` 必須維持 `Pass: 121 (100.0%), Fail: 0, Skip: 0, Unknown: 0`，達成 0 邏輯破壞。 |
| **NFR-03** | 發布邊界守門 | 嚴格維持軌道 A (`@build`) 本地直裝物化，嚴禁在未獲授權情況下執行 `dev bump` 或 `dev release`。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `DN-DEV-08`：測試套件採用 3-State 分類，所有用例成功時必須調用 `self.mark_passed()` 避免標記為 UNKNOWN。
- **`[!IMPORTANT]`** 模組內部跨空間存取必須使用語意 URI，不可硬編碼實體檔案系統相對路徑。
- **`[!IMPORTANT]`** `KnowledgeEngine` 所有原本在頂層模組被外部直接匯入的型別與常數（如 `AUTO_BUDGET_CHARS`、`compute_dynamic_snippet_lines` 等）需在 `engine.py` 保留轉發匯出，確保相容現有測試與呼叫者。
