# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 模組 SPICE 網表語系解譯器 (SpiceParser) 整合  
> 建立日期：2026-08-29  
> 所屬主計畫：無  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在 API 規格書與 `SpiceParser` 設計中均有具體承接。
- [x] **邊界防護**：EC-01 ~ EC-04 在 Stage 1 與 Stage 2 狀態機中有明確防護解法。
- [x] **依賴純淨**：符合 NFR-01/NFR-02 指標約束（純 Python 實作、零外部依賴、高解析效能）。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1** | `source/knowledge-db/README.md` | Modify | 於多語言解析矩陣新增 SPICE (`.cir`, `.sp`, `.spice`, `.net`, `.cdl`) 支援說明與檢索範例。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：若網表出現巨大連續行（例如接續符號 `+` 連續超過 500 行，包含大量 Pin 清單與模型參數），行聚合器是否會造成效能瓶頸或行號錯位？**  
> 💡 **防護解法**：Stage 1 邏輯行聚合器採用單次 O(N) 線性掃描器與字串 List Buffer 收集機制，並在遇到非 `+` 行時一次性 `join`，同時紀錄當前累積的真實檔案行號，確保百萬行大型網表毫秒級重構且零行號漂移。

> ❓ **尖銳問題 2：若 SPICE 網表出現首行標題（Title Line）且剛好以看似元件的字元開頭（例如 `MY_FILTER_CIRCUIT`），解析器如何避免誤判為元件宣告？**  
> 💡 **防護解法**：Stage 2 狀態機進行首行防護判定：第 1 個邏輯行若非以 `.` 指令開頭且無法解析為合法元件前綴語法時，自動視為 Title Line / 說明註解安全跳過，杜絕誤判。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：擴充 `schema.py`，新增 `LanguageType.SPICE = "spice"`。
- [ ] **TASK-02**：實作 `spice_parser.py`（Stage 1 行聚合器與 Stage 2 階層狀態機）。
- [ ] **TASK-03**：於 `parsers/__init__.py` 與 `registry.py` 導出並預設註冊 `SpiceParser`。
- [ ] **TASK-04**：撰寫 `test_spice_parser.py` 完整單元與邊界測試套件 (FT-01~05, ET-01~04)。
- [ ] **TASK-05**：更新 `source/knowledge-db/README.md` 說明文檔。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿驗證**：核可 `P02_architecture_plan.md`、`P03_api_spec.md` 與 `P06_test_plan.md`，即刻啟動 Phase 5 依序程式碼實作。
