# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：優化 knowledge-db 輸出搜尋結果時的格式  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/`  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > 改為多模式
  > 1. 簡易模式，即為預設模式，極輕量顯示排名 + 檔案位置
  > 2. 詳細模式，現有狀況
- **核心目標**：
  - **預設模式 (簡易模式 / Simple Mode)**：以極輕量單行排版輸出，僅展示搜尋排名與檔案定位路徑（含行號），大幅降低終端資訊雜訊，方便快速瀏覽與點擊跳轉。
  - **詳細模式 (Detailed Mode)**：透過特定參數（如 `--detail` / `-d` / `--verbose`）觸發，完整保留現有排版資訊（包含 Score 評分、符號類型、符號名稱、語言、簽名、摘要說明與命中關鍵詞）。
  - **結構化模式 (JSON Mode)**：支援 `--json` 旗標輸出標準結構化 JSON 物件，供自動化腳本或工具鏈調用。
- **邊界排除 (Explicitly Excluded)**：
  - 檢索演算法本體與 BM25 權重計分維持不變，僅針對 CLI 終端輸出呈現進行多模式格式化升級。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 子計畫定位**：歸屬於模組工具鏈優化主計畫 `plans://2026_08_28_1754_module_toolchain_optimization/` 下之子計畫 `sub_07_knowledge_db_search_output_formatting`。
- **[P00:DR-02] 多模式輸出策略**：
  - 預設模式（簡易）：每筆結果單行極簡輸出，格式為 `#<Rank> <file_path>:<line_number>`。
  - 詳細模式：附加 `--detail`（或 `-d` / `--verbose`）參數時輸出完整多行結構。
  - JSON 模式：附加 `--json` 參數時輸出完整查詢與結果清冊之 JSON 結構。
- **[P00:DR-03] 分流判定**：採用 Full Track (Level 1) 並由開發者授權 `/Auto` 工作流連續推進。

---

## 3. 開放議題與確認紀錄

- [x] 輸出模式架構確立（預設簡易模式 + 詳細模式參數切換）。
- [x] 簡易模式單行呈現格式確認（極簡 `#01 <file_path>:<line_number>`）。
- [x] 詳細模式觸發旗標確認（`--detail` / `-d` / `--verbose`）。
- [x] 結構化輸出旗標確認（`--json`）。
