# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：knowledge-db 子計畫 01: 空間管理與資料架構 (Space Management & Data Schema)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 依據 P02：[P02_architecture_plan.md](./P02_architecture_plan.md)  
> 依據 P03：[P03_api_spec.md](./P03_api_spec.md)  
> 測試計畫：[P06_test_plan.md](./P06_test_plan.md) (Confirmed)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-10 在 `P03_api_spec.md` 中均有具體承接之 Class、Method 或 Config 檔案。
- [x] **邊界防護**：EC-01 ~ EC-08 在 `SpaceConfig`、`SpaceManager`、`FingerprintScanner` 與例外體系中均已規劃具體防禦邏輯。
- [x] **依賴純淨**：NFR-01 ~ NFR-04 承諾 100% Python 3 原生標準庫、I/O 初篩極小化、`YSCBTestCase` 沙盒跑測與 Dogfooding 源碼空間邊界。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1 (概覽)** | `docs/knowledge-db/README.md` | **New** | `knowledge-db` 模組定位、架構概覽與子計畫演進路徑 |
| **維度 2 (指南)** | `docs/knowledge-db/contributes_guide.md` | **New** | 指導其他模組透過 `contributes.knowledge-db` 注入 Space 與 Thesaurus 之實踐指南 |
| **維度 3 (架構)** | `docs/knowledge-db/architecture.md` | **New** | 空間管理雙軌聚合、全空間聯集 (Union Scope) 與雙階增量指紋比對核心架構細節 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：當大量檔案（數萬個）同時掃描且部分檔案在掃描期間被外部修改或刪除時，如何保證指紋庫不會發生狀態不一致或寫入競態？**  
> 💡 **防護解法**：每個檔案在掃描迴圈中獨立執行 `os.stat` 與安全讀取；若讀取期間檔案被刪除或鎖定（拋出 `FileNotFoundError` / `PermissionError`），系統捕獲異常並記錄 Warning 略過；指紋持久化採用原子寫入機制（先寫入帶 UUID 之暫存檔再使用 `os.replace`），確保任何中斷都不會留下損毀的 `fingerprints.json`。

> ❓ **尖銳問題 2：當 Donor 模組注入之 `include` 路徑不存在或指向外部未初始化的無效 URI 時，是否會導致系統崩潰或死鎖？**  
> 💡 **防護解法**：`SpaceManager.resolve_space_include` 對所有 URI 進行安全解析，並驗證 `p.exists()`；對於無效或不存在之路徑僅發出 Warning 日誌並予以過濾，維持其餘合法來源的正常處理，徹底杜絕單點目錄故障擴散至全域。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (基礎例外定義)**：實作 `source/knowledge-db/knowledge_db/exceptions.py`，定義 `KnowledgeDBError` 及其子類。
- [ ] **TASK-02 (核心資料模型)**：實作 `source/knowledge-db/knowledge_db/schema.py`，包含 `SymbolKind`、`LanguageType`、`SpaceOrigin`、`MemberInfo`、`UnifiedSymbol`（SHA1 ID 計算）、`SpaceConfig`（預設 include all 邏輯）、`ThesaurusConfig`。
- [ ] **TASK-03 (空間管理與聚合)**：實作 `source/knowledge-db/knowledge_db/space.py`，提供 `SpaceManager` 雙軌聚合、優先權覆蓋 (`Local` > `Project` > `Contributed`)、全空間聯集 (`get_union_spaces`)、語意 URI 解算與 VFS 目錄定位。
- [ ] **TASK-04 (雙階增量比對引擎)**：實作 `source/knowledge-db/knowledge_db/scanner.py`，包含 `FileFingerprint`、`ScanDiffResult`、`FingerprintScanner`（Stage 1 mtime+size 初篩 + Stage 2 SHA1 校驗、全空間聯集掃描、快取損毀自癒與原子寫入）。
- [ ] **TASK-05 (模組骨架與元數據)**：建立 `source/knowledge-db/manifest.json`、`config.project.json`、`contributes.format.md`、`scripts/__init__.py`、`scripts/cli.py` 與 `knowledge_db/__init__.py`。
- [ ] **TASK-06 (單元測試套件)**：實作 `source/knowledge-db/tests/` 套件（`test_schema.py`, `test_space.py`, `test_scanner.py`），繼承 `YSCBTestCase` 覆蓋 FT-01~09、ET-01~03 與 RT-01。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性定稿實作計畫與測試清單**：確認 Phase 1~3 規格與依賴拓撲無誤，同步定稿 `P06_test_plan.md` 為 `Confirmed`，進入 Phase 5 編碼實作。
