# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：優化 knowledge-db 輸出搜尋結果時的格式  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/`  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-04 在 API 規格書與 CLI 路由中有對應介面承接
- [x] **邊界防護**：EC-01 ~ EC-03 具備 0 結果優雅處理與參數優先級防禦策略
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 純標準庫與 UTF-8 編碼保護約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 3 (API/CLI)** | `docs/knowledge-db/user_guide.md` | Modify | 補充 `search` 輸出多模式參數 (`--detail`, `--json`) 與預設簡易單行輸出說明 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當搜尋結果中包含未註冊副檔名或非文字格式之符號，單行格式輸出是否會因路徑過長或異常字符導致控制台錯亂？  
> 💡 **防護解法**：`_format_simple` 直接提取正規化之 `sym.file_path` 與 `sym.line_number`，配合 sys.stdout UTF-8 編碼保護，確保即使長路徑或特殊字元亦可穩定輸出。

> ❓ **尖銳問題 2**：若使用者在管線腳本中調用 `python yscb.py knowledge-db search <query> --json`，輸出是否會夾帶非 JSON 的除錯日誌？  
> 💡 **防護解法**：當啟用 `--json` 時，直接向 stdout 輸出乾淨的 `json.dumps(...)` 字串並立即 return 0，不輸出任何多餘的 banner 或裝飾線，確保 `jq` 或 Python `json.loads` 可 100% 正確解析。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：在 `source/knowledge-db/scripts/cli.py` 中實作 `_format_simple`、`_format_detailed`、`_format_json` 輔助函式，並於 `main` 路由中整合 `--detail` / `-d` / `--verbose` 與 `--json` 旗標解析。
- [ ] **TASK-02**：在 `source/knowledge-db/tests/test_cli.py` 中撰寫 FT-01 ~ FT-03 與 ET-01 ~ ET-02 完整單元測試。
- [ ] **TASK-03**：執行全模組沙盒測試驗證 (`python yscb.py dev test knowledge-db`)，確保回歸與新測試 100% 通過。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 格式化定稿**：簡易模式以 `#<Rank:02d> <file_path>:<line_number>` 作為唯一標準單行輸出；詳細模式完整保留現有欄位。
