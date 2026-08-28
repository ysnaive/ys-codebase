# 需求規格說明書 (Requirements Specification)

> 功能名稱：knowledge-db 子計畫 01: 空間管理與資料架構 (Space Management & Data Schema)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 / 決策 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **模組骨架建立與 Manifest 宣告** | 在 `source/knowledge-db/` 建立標準 YSCB 模組骨架（`manifest.json`, `contributes.format.md`, `config.project.json`, `scripts/cli.py`, `knowledge_db/`, `tests/`）。宣告 `name: "knowledge-db"`, `version: "0.1.0.0"`, `dependencies: {"core": ">=1.0.0"}`，並宣告 URI Scheme `knowledge.storage -> storage://knowledge-db/`。 | P0 | [P00:DR-01] |
| **FR-02** | **核心列舉型別與成員資料模型** | 定義 `SymbolKind`（代碼類與 Markdown 文檔類）、`LanguageType`、`SpaceOrigin` 列舉；實作 `MemberInfo`（`name`, `kind`, `signature`, `docstring`, `visibility`, `line_number`），支援 `to_dict()` 與 `from_dict()` 序列化。 | P0 | [P00:DR-02] |
| **FR-03** | **統一符號資料模型 (`UnifiedSymbol`)** | 實作不可變 `UnifiedSymbol` 模型（`id`, `name`, `kind`, `file_path`, `line_number`, `language`, `docstring`, `signature`, `members`, `metadata`）。實作唯一 ID 計算演算法 `compute_id(space, file_path, name, kind, line_number) -> sha1_hex`，支援無損 `to_dict()` 與 `from_dict()` 序列化。 | P0 | [P00:DR-02] |
| **FR-04** | **空間與同義詞組態模型 (`SpaceConfig` & `ThesaurusConfig`)** | 實作獨立解耦之 `SpaceConfig`（`name`, `description`, `include`, `exclude`, `file_patterns`, `origin`），提供 `is_file_included(filename)` 比對邏輯（`file_patterns` 省略或未定義時預設 include all）；實作獨立解耦之 `ThesaurusConfig`（`groups: List[List[str]]`, `origin`）。兩者均支援 `to_dict()` 與 `from_dict()`。 | P0 | [P00:DR-02] |
| **FR-05** | **雙軌來源空間定義與多空間聚合 (SpaceManager)** | 實作 `SpaceManager` 核心管理器，支援雙軌來源聚合：<br/>1. **模組聯動注入**：讀取 Donor 模組之 `contributes.knowledge-db.json` 或 `manifest.json`。<br/>2. **2x2 組態宣告與覆蓋**：讀取 `config.project.json` 與 `config.local.json`。<br/>依優先權 `Local Config` > `Project Config` > `Module Contributes` 進行同名空間與同義詞覆蓋合併。 | P0 | [P00:DR-03] |
| **FR-06** | **全空間聯集處理架構 (Union Scope Architecture)** | 消除單一 `default_space` 強制約定，以全系統所有有效空間之聯集作為全域處理範圍。提供 `get_union_spaces()` 回傳所有已註冊空間清單；實作 `resolve_space_include(space_name)` 將語意 URI 解算為本機實體絕對路徑清單；實作 `get_space_storage_dir(space_name)` 定位 VFS 存儲路徑。 | P0 | [P00:DR-03] |
| **FR-07** | **雙階增量檔案指紋比對引擎 (Two-Stage Fingerprint Engine)** | 實作 `FileFingerprint` 與 `ScanDiffResult` 模型；實作 `FingerprintScanner` 雙階比對演算法：<br/>- **Stage 1 (初篩)**：比對 `mtime` 與 `size`，一致則直接標記 `UNCHANGED` 略過後續 I/O。<br/>- **Stage 2 (校驗)**：Stage 1 不符時讀取檔案計算 `SHA1`，一致則更新快取 `mtime` 並標記 `UNCHANGED`，不一致則標記 `MODIFIED`。<br/>- 新增檔案標記 `ADDED`，磁碟遺失檔案標記 `DELETED`。 | P0 | [P00:DR-04] |
| **FR-08** | **全空間聯集增量掃描與指紋庫持久化** | 實作 `scan_space(space_config, force=False)` 執行單一空間增量掃描；實作 `scan_all_spaces(spaces=None, force=False)` 執行全空間聯集增量掃描，回傳 `{space_name: ScanDiffResult}`。實作 `load_fingerprints` 與 `save_fingerprints` 原子寫入持久化機制。 | P0 | [P00:DR-04] |
| **FR-09** | **專屬例外體系與邊界防禦** | 實作專屬例外階層：`KnowledgeDBError`、`SpaceNotFoundError`、`InvalidSpaceConfigError`、`SchemaValidationError`、`FingerprintCorruptedError`。提供快取損毀自癒、無效路徑過濾與 UTF-8 編碼安全防禦。 | P0 | [P00:DR-05] |
| **FR-10** | **擴充點規範說明文件與專案組態範本** | 產出 `source/knowledge-db/contributes.format.md` 規範說明書，供其他 Donor 模組依循宣告 `spaces` 與 `thesaurus`；產出預設 `config.project.json` 範本。 | P0 | [P00:DR-01], [P00:DR-03] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | **空間組態未宣告 `file_patterns` 或設為空** | `SpaceConfig.is_file_included()` 預設全包含 (include all)，所有非 `exclude` 排除之檔案均正常納入掃描。 |
| **EC-02** | **空間 `include` 包含不存在或無法訪問之語意 URI / 路徑** | `resolve_space_include` 記錄 Warning 日誌並自動略過該無效來源，不阻斷其他合法來源路徑的解析與掃描。 |
| **EC-03** | **指紋庫快取檔案 `fingerprints.json` 損毀或格式非合法 JSON** | `load_fingerprints` 捕獲 `JSONDecodeError`，發出 Warning 日誌並自動自癒初始化為空字典，降級為全量掃描 (全部標記為 Added)，並於掃描後原子覆蓋修復。 |
| **EC-04** | **檔案經 touch 變更 `mtime` 但內容未修改** | Stage 1 比對發現 `mtime` 不一致 ➔ 進入 Stage 2 計算 `SHA1` 發現內容相同 ➔ 僅更新快取中的 `mtime` 並判定為 `UNCHANGED`，不產生偽變更。 |
| **EC-05** | **掃描過程中遭遇無權限讀取之個別檔案** | `FingerprintScanner` 捕獲 `OSError` / `PermissionError`，發出 Warning 日誌並略過該檔案，保證其餘檔案正常掃描。 |
| **EC-06** | **檔案包含非 UTF-8 字元或特殊二進位編碼** | 讀取文字內容時一律使用 `utf-8` 搭配 `errors="replace"` 容錯轉譯，防止編碼異常中斷掃描。 |
| **EC-07** | **同名空間於模組注入與專案組態中重複定義** | 依階層優先權 `Local Config` > `Project Config` > `Module Contributes` 進行覆蓋，並於生成的 `SpaceConfig` 正確標註 `origin`。 |
| **EC-08** | **查詢不存在或未註冊之空間名稱** | `SpaceManager.get_space(name)` 拋出結構化 `SpaceNotFoundError`，提供明確錯誤訊息。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **零外部相依 (Zero External Dependency)** | 100% 採用 Python 3.9+ 原生標準庫（`dataclasses`, `pathlib`, `hashlib`, `json`, `fnmatch`, `logging` 等），嚴禁引入任何第三方相依套件。 |
| **NFR-02** | **極致 I/O 效能 (Minimal I/O)** | 雙階增量比對在無檔案修改情境下僅執行 `os.stat` 讀取元數據 (Stage 1)，0 次檔案內容讀取與 0 次 SHA1 計算。 |
| **NFR-03** | **測試品質守門 (Test-Driven Quality Gate)** | 單元測試 100% 繼承 `YSCBTestCase`，在沙盒環境驗證，模組單元測試 100% Passed。 |
| **NFR-04** | **空間協議與 Dogfooding 邊界 (Space Protocol & Boundaries)** | 模組原始碼 100% 位於 `source/knowledge-db/`，路徑解析完全透過 Core URI 協議（`module://`, `storage://`, `project://`），嚴禁手動直接修改 `modules/` 運行端。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- > [!IMPORTANT]
  > **零外部相依約束**：`knowledge-db` 為基礎設施模組，必須 100% 使用 Python 原生標準庫，絕不可使用第三方庫（如 pydantic, numpy 等）。

- > [!IMPORTANT]
  > **無 default_space 之聯集處理公理**：系統不依賴單一預設空間，未限定空間之全域操作以所有有效空間之聯集 ($Scope = \bigcup Space_i$) 作為處理範圍。

- > [!WARNING]
  > **指紋快取原子寫入機制**：指紋存儲必須採用原子寫入機制（先寫入暫存檔再使用 `os.replace`），防止進程異常中斷導致 `fingerprints.json` 損毀。
