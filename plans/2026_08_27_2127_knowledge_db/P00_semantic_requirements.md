# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：knowledge-db 模組開發 (Knowledge Database Module)  
> 建立日期：2026-08-27  
> 所屬主計畫：無 (分類型主計畫 Umbrella)  
> 狀態：Draft  
> 計畫類型：Feature  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：目前打算開發一個新的 module:knowledge-db，主要功能為，可定義資料庫空間，進行語意打包，並提供語意化搜尋功能，先建立分類型計畫。
- **核心目標**：
  1. 建立 `knowledge-db` 模組開發之分類型主計畫 (Umbrella Plan)。
  2. 統籌模組三大核心能力：資料庫空間定義 (Database Space Definition)、語意打包 (Semantic Bundling/Packaging)、以及語意化搜尋 (Semantic Search)。
- **邊界排除 (Explicitly Excluded)**：待討論釐清。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 開立分類型主計畫**：依開發者指示開立 Umbrella 主計畫 `plans://2026_08_27_2127_knowledge_db/`，後續依功能模組拆分子計畫推進。
- **[P00:DR-02] 參考 GC_VEX_V5 原型架構實踐**：
  - 核心優勢延續：100% 免外部相依 (Zero External Dependency，純 Python 3 標準庫)、多語言統一符號模型 (`UnifiedSymbol`)、CJK/CamelCase/snake_case 混合分詞器 (`CodeTokenizer`)、中文/英文領域同義詞庫 (`Thesaurus`)、倒排索引多欄位加權 BM25 檢索、以及 SHA1+mtime 增量快取機制。
  - 升級演進目標：由原本單一專案硬編碼路徑升級為具備「資料庫空間定義 (Database Space)」、「語意打包 (Semantic Bundling)」與「語意化搜尋 (Semantic Search)」之標準 YSCB 模組。
- **[P00:DR-03] 產出 R01 調研報告與四大維度拆分**：
  - 產出 `R01_knowledge_db_architecture_and_taxonomy.md` 專題技術調研報告。
  - 確立全系統拆分為四大子系統維度：維度 ① 空間管理、維度 ② 解析與打包、維度 ③ 分詞與檢索、維度 ④ CLI 與生態整合。
  - 主計畫規劃拆分為 `sub_01` ~ `sub_04` 四個循序推進之子計畫。

---

## 3. 開放議題與確認紀錄

- [ ] **確認 1 (四大維度劃分)**：開發者是否認同將系統劃分為「空間管理」、「解析打包」、「分詞檢索」、「CLI與生態」四大維度？
- [ ] **確認 2 (子計畫拆分矩陣)**：開發者是否同意依 `sub_01` (空間與Schema) $\rightarrow$ `sub_02` (解析與打包) $\rightarrow$ `sub_03` (分詞與BM25) $\rightarrow$ `sub_04` (CLI與生態) 之路線循序執行？
- [ ] **確認 3 (設計細節覆核)**：R01 中所載之統一符號 Schema、多欄位加權比重、2x2 組態格式是否確認無誤？
