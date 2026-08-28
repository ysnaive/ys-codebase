# 架構設計說明書 (Architecture Design)

> 功能名稱：knowledge-db 子計畫 01: 空間管理與資料架構 (Space Management & Data Schema)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_27_2127_knowledge_db/`  
> 狀態：Confirmed  
> 依據 P01：[P01_requirements_spec.md](./P01_requirements_spec.md)  
> 模板版本：v1.2  

---

## 1. 模組架構分層與職責邊界 (Layered Architecture)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       knowledge-db CLI 入口層 (scripts/cli.py)              │
│         提供子指令骨架、參數解析與 SpaceManager / Scanner 調度介面          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    空間管理層 (knowledge_db/space.py)                       │
│  SpaceManager: 雙軌來源聚合 (Contributes + Config)、無 default_space 聯集   │
│  路徑解算 (resolve_space_include)、VFS 存儲目錄定位 (get_space_storage_dir) │
└──────────────────┬───────────────────────────────────┬──────────────────────┘
                   │                                   │
┌──────────────────▼───────────────────┐ ┌─────────────▼──────────────────────┐
│  增量指紋掃描層 (scanner.py)         │ │  資料模型與 Schema 層 (schema.py)  │
│  FingerprintScanner: 雙階比對引擎    │ │  UnifiedSymbol, MemberInfo         │
│  Stage 1 (mtime+size) + Stage 2(SHA1)│ │  SpaceConfig, ThesaurusConfig      │
│  FileFingerprint, ScanDiffResult     │ │  SymbolKind, LanguageType, Enums   │
│  原子寫入持久化 & 自癒容錯           │ │  to_dict / from_dict 序列化        │
└──────────────────┬───────────────────┘ └─────────────┬──────────────────────┘
                   │                                   │
┌──────────────────▼───────────────────────────────────▼──────────────────────┐
│               基礎例外層 (knowledge_db/exceptions.py)                        │
│  KnowledgeDBError, SpaceNotFoundError, InvalidSpaceConfigError, ...         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    YSCB 核心基礎設施 (core.uri, stdlib)                     │
│  Core URI 協議 (module://, storage://, project://) & Python 3 標準庫        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心資料流與循序圖 (Data Flow & Sequence Diagram)

### 2.1 雙軌空間聚合與聯集解算循序 (SpaceManager Aggregation)

```mermaid
sequenceDiagram
    autonumber
    participant Client as 呼叫端 / CLI
    participant SM as SpaceManager
    participant Core as Core Contributes / Config
    participant FS as 實體檔案系統

    Client->>SM: load_spaces()
    SM->>Core: 讀取所有模組之 contributes.knowledge-db.json / manifest.json
    Core-->>SM: 回傳模組注入之空間清單 (origin: module:<donor>)
    SM->>Core: 讀取 config.project.json
    Core-->>SM: 回傳專案宣告之空間清單 (origin: project)
    SM->>Core: 讀取 config.local.json (若存在)
    Core-->>SM: 回傳本機覆蓋之空間清單 (origin: local)
    SM->>SM: 依 Local > Project > Contributed 優先權合併同名空間
    SM-->>Client: Dict[str, SpaceConfig] (所有有效空間)

    Client->>SM: resolve_space_include(space_name)
    loop 遍歷 space_config.include
        SM->>Core: resolve_uri(uri)
        Core-->>SM: 絕對路徑 Path
        SM->>FS: 檢查路徑是否存在
        alt 路徑存在
            SM->>SM: 納入有效路徑清單
        else 路徑不存在
            SM->>SM: 發出 Warning 日誌並略過 (EC-02)
        end
    end
    SM-->>Client: List[Path] (解析後實體來源路徑清單)
```

### 2.2 雙階增量指紋比對循序 (Two-Stage Fingerprint Scanning)

```mermaid
sequenceDiagram
    autonumber
    participant Client as 呼叫端 / 建立索引程序
    participant Scanner as FingerprintScanner
    participant Storage as VFS Storage (fingerprints.json)
    participant FS as 來源目錄 (實體檔案)

    Client->>Scanner: scan_space(space_config, force=False)
    Scanner->>Storage: load_fingerprints(space_name)
    alt 檔案存在且合法
        Storage-->>Scanner: Dict[relpath, FileFingerprint] (舊指紋快取)
    else 檔案不存在
        Scanner->>Scanner: 初始化為空字典
    else 檔案損毀 (EC-03)
        Scanner->>Scanner: 發出 Warning，自癒重置為空字典 (全量比對)
    end

    loop 遍歷所有來源檔案 (符合 file_patterns 且未被 exclude)
        Scanner->>FS: os.stat(file_path) -> (mtime, size)
        alt force == False 且 舊快取存在 且 mtime == old.mtime 且 size == old.size (Stage 1)
            Scanner->>Scanner: 標記 UNCHANGED (0 次內容讀取, 0 次 SHA1)
        else Stage 1 不符 / 全新檔案 / force == True (Stage 2)
            Scanner->>FS: 讀取檔案二進位內容
            Scanner->>Scanner: 計算 SHA1 雜湊
            alt 舊快取存在 且 sha1 == old.sha1
                Scanner->>Scanner: 僅更新快取 mtime，標記 UNCHANGED (EC-04)
            else 舊快取不存在
                Scanner->>Scanner: 建立新 FileFingerprint，標記 ADDED
            else sha1 != old.sha1
                Scanner->>Scanner: 建立新 FileFingerprint，標記 MODIFIED
            end
        end
    end

    loop 檢驗舊指紋庫中未被訪問之檔案
        Scanner->>Scanner: 標記 DELETED
    end

    Scanner->>Storage: save_fingerprints(space_name, updated_fingerprints) [原子寫入]
    Scanner-->>Client: ScanDiffResult (added, modified, deleted, unchanged)
```

---

## 3. 受影響檔案與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `source/knowledge-db/manifest.json` | **New** | 模組元數據、依賴 `core >= 1.0.0` 與 `knowledge.storage` URI 宣告 |
| `source/knowledge-db/config.project.json` | **New** | 預設專案層級組態範本（宣告 `project_main` 空間範例） |
| `source/knowledge-db/contributes.format.md` | **New** | 擴充點規格說明文件，指導其他 Donor 模組注入空間與同義詞 |
| `source/knowledge-db/scripts/__init__.py` | **New** | CLI scripts 套件初始化 |
| `source/knowledge-db/scripts/cli.py` | **New** | CLI 進入點骨架與參數路由器 |
| `source/knowledge-db/knowledge_db/__init__.py` | **New** | 模組核心套件導出 (`SpaceManager`, `FingerprintScanner`, `UnifiedSymbol`, ...) |
| `source/knowledge-db/knowledge_db/exceptions.py` | **New** | 專屬例外階層 (`KnowledgeDBError`, `SpaceNotFoundError`, ...) |
| `source/knowledge-db/knowledge_db/schema.py` | **New** | 核心資料結構、Enums、序列化與 ID 計算演算法 |
| `source/knowledge-db/knowledge_db/space.py` | **New** | `SpaceManager` 多空間雙軌聚合、優先權覆蓋與路徑解算 |
| `source/knowledge-db/knowledge_db/scanner.py` | **New** | `FingerprintScanner` 雙階增量比對引擎與原子持久化 |
| `source/knowledge-db/tests/__init__.py` | **New** | 測試套件初始化 |
| `source/knowledge-db/tests/test_schema.py` | **New** | `UnifiedSymbol`, `MemberInfo`, `SpaceConfig`, Enums 單元測試 |
| `source/knowledge-db/tests/test_space.py` | **New** | `SpaceManager` 雙軌聚合、優先權與 URI 解算單元測試 |
| `source/knowledge-db/tests/test_scanner.py` | **New** | `FingerprintScanner` 雙階比對、變更偵測、自癒與原子寫入單元測試 |

---

## 4. 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] 零外部相依與不可變資料結構**：核心資料模型 `UnifiedSymbol`、`MemberInfo`、`FileFingerprint` 採用 `@dataclass(frozen=True)`，完全使用 Python 3 原生標準庫（`hashlib`, `pathlib`, `json`, `fnmatch`），確保極致執行效能與全平台相容性。
- **[P02:DR-02] 依賴注入與沙盒測試架構**：`SpaceManager` 與 `FingerprintScanner` 支援傳入 `core_context` 或自訂 `config_dir`/`storage_dir`，使其在測試中可在隔離虛擬沙盒中獨立運作，杜絕全域狀態污染。
- **[P02:DR-03] 原子寫入與快取自癒機制**：指紋存儲採用 `NamedTemporaryFile` 寫入後以 `os.replace` 原子替換目標檔案；若快取損毀自動降級為全量掃描並修復，達成高強韌度（Resilience）。
