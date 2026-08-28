# 需求規格說明書 (Requirements Specification)

> 功能名稱：優化 knowledge-db 輸出搜尋結果時的格式  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/`  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 預設簡易單行排版輸出 (Simple Mode) | 當使用者未帶額外排版參數時，`search` 結果以極簡單行格式輸出，格式為 `#<Rank:02d> <file_path>:<line_number>`，消除冗餘資訊。 | P0 | [P00:DR-02] |
| **FR-02** | 詳細模式輸出支援 (Detailed Mode) | 當使用者傳入 `--detail`、`-d` 或 `--verbose` 旗標時，輸出完整多行排版，包含評分 (Score)、符號類型、符號名稱、程式語言、檔案行號、簽名、摘要說明與命中關鍵字。 | P0 | [P00:DR-02] |
| **FR-03** | 結構化 JSON 輸出支援 (JSON Mode) | 當使用者傳入 `--json` 旗標時，將搜尋結果包裝為標準 JSON 格式輸出（包含 `query`, `total`, `results` 陣列），支援 stdout 管道處理。 | P1 | [P00:DR-02] |
| **FR-04** | CLI Help 說明文字更新 | 於 `knowledge-db --help` 說明中補充 `search` 之 `--detail` / `-d` 與 `--json` 用法提示。 | P1 | [P00:DR-02] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 檢索查詢未找到任何匹配結果 (0 結果) | 簡易與詳細模式輸出友善提示 `[knowledge-db] 檢索查詢: '<query>' (未找到符合的結果)`；JSON 模式輸出 `{"query": "<query>", "total": 0, "results": []}`。 |
| **EC-02** | 未傳入檢索查詢字串 (`search` 缺少參數) | 輸出錯誤訊息至 stderr，並回傳 Exit Code 1。 |
| **EC-03** | 同時帶有多個排版旗標 (如 `--json` 與 `--detail`) | `--json` 優先級最高，直接輸出 JSON 結構，避免非預期字符破壞 JSON 解析。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 零外部依賴 (Zero Dependency) | 100% 採用 Python 原生標準庫（`sys`, `json`, `os`），嚴禁引入第三方套件。 |
| **NFR-02** | 效能與即時性 | 格式化處理耗時 $< 5\text{ms}$，不增加檢索延遲。 |
| **NFR-03** | 編碼相容性 | 終端輸出維持 Windows 控制台 UTF-8 編碼保護。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** `knowledge-db` 的 AST 分析與檢索皆依賴純 Python 標準庫，格式化輸出應直接基於 `SearchResult` 物件屬性進行渲染。
