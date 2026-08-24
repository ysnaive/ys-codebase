# YS-Codebase (`ys-codebase`)

> 一套 100% Python 標準庫、零第三方依賴、現代化模組化微內核架構之 AI Agent 代碼庫工程工具與規範管理系統。

---

## 🌟 核心架構特色

1. **超薄無狀態宿主 (Ultra-Thin Host `yscb.py`)**：
   - 專案根目錄僅需單一 `yscb.py` 宿主腳本與 `yscb.config.json`，負責路徑定位、自舉與動態命令派發。
2. **微內核基礎設施 (Microkernel `core`)**：
   - 提供 First-Class VFS SDK（`core.uri`）、`AtomicEngine` 12 大原子操作生命週期、`Installer` 套件管理器與 `ContributesAggregator` 依賴注入快取。
3. **語意空間協議 (Semantic URI Protocol)**：
   - 提供 14 組自注入標準協議（`yscb://`, `config://`, `cache://`, `temp://`, `mirror://`, `snapshot://`, `module://`, `module.source://`, `module.build://` 等），以及具備零 Fallback 安全阻斷的 `project://`。
4. **開發者工具鏈生態 (`dev`)**：
   - 內建 `dev create` 模組腳手架、`dev check` 靜態合規檢查器、`dev build` 純淨套件打包器與 `dev test` 雙階段測試/Auto-Contract 動態契約合成引擎。
5. **精準命名空間 Hook 對接 (`scripts/hook.{emit_module}.py`)**：
   - 模組間透過以發起端命名的 Hook 檔案對接生命週期事件，內建 `ExecutionContext` 介面與例外隔離保護。
6. **2x2 設定與中介快取矩陣 (The 2x2 Matrix & Cache Layer)**：
   - 專案設定（`config.project.json`）進 Git 版控；個人覆蓋（`config.local.json`）忽略；系統衍生之中介層物化快照（`contributes.merged.json`）全面收斂至 `cache://`。

---

## 📁 倉庫目錄結構

```text
ys-codebase/ (專案根目錄，代表 "project://" / ":/")
├── yscb.py                            # [超薄宿主] 統一指令轉發與核心自舉進入點
├── yscb.config.json                   # [全域組態] 宣告 yscb_root、預設源與已安裝模組
├── AGENTS.md                          # [AI 準則] 專案 AI Agent 行為準則與硬性規範
├── README.md                          # [專案首頁] 本手冊
│
├── docs/                              # [系統知識庫] 專案知識庫 (docs://)
│   ├── README.md                      # 全域架構地圖與導覽索引
│   ├── _project/STANDARDS.md          # 全專案工程規範與邊界標準
│   ├── core/                          # Core 微內核架構、URI 協議、Hook 手冊與 DN 註記
│   └── dev/                           # Dev 工具鏈、測試框架指南與 DN 註記
│
├── plans/                             # [進行中計畫] 活躍開發計畫目錄 (plans://)
├── archive_plans/                     # [歷史計畫] 已封存歷史計畫目錄 (archive://)
│
└── ys_codebase/                       # [工具庫核心環境 (yscb://)]
    ├── modules/                       # [運行端空間] 本地安裝之純淨代碼 (module.root://)
    │   ├── core/                      # Core 微內核運行端
    │   └── dev/                       # Dev 開發者工具箱運行端
    ├── source/                        # [源碼開發空間] 模組源碼 SSOT (module.source.root://)
    │   ├── core/                      # Core 原始碼
    │   └── dev/                       # Dev 原始碼
    ├── build/                         # [套件庫空間] 本機 Provider 發布物 (module.build.root://)
    │   ├── core/1.0.0/                # Core 版本化純淨產物
    │   └── dev/1.0.0/                 # Dev 版本化純淨產物
    ├── config/                        # [模組設定空間] 專案層級組態資產 (config.root://)
    │   └── core/config.project.json   # Core 專案設定 (宣告 project_root)
    ├── .cache/                        # [快取空間] 系統中介層物化快照 (cache.root://)
    │   └── core/contributes.merged.json
    ├── .mirror/                       # [鏡像庫] 本地下載鏡像快照 (mirror://)
    ├── .temp/                         # [暫存區] 跨程序鎖與測試隔離沙盒 (temp://)
    └── .snapshots/                    # [快照庫] 系統組態歷史備份 (snapshot://)
```

---

## 🚀 快速上手 (Quick Start)

### 1. 系統初始化 (`init`)
```bash
python yscb.py init ./ys_codebase
```

### 2. 安裝與管理模組 (`install` / `update` / `remove`)
```bash
# 安裝模組
python yscb.py install dev

# 檢查已安裝模組與健康度
python yscb.py list
python yscb.py status

# 更新環境與刷新依賴注入
python yscb.py reload
```

### 3. 模組開發與測試 (`dev`)
```bash
# 建立新模組
python yscb.py dev create my_module

# 靜態合規檢查
python yscb.py dev check --all

# 純淨套件打包
python yscb.py dev build --all --clean

# 執行全量測試 (Auto-Contract + Custom Tests)
python yscb.py dev test --all --verbose
```

---

## 📚 系統知識庫快速跳轉

- [全域知識地圖與導覽 (docs/README.md)](docs/README.md)
- [核心工程規範與邊界架構 (docs/_project/STANDARDS.md)](docs/_project/STANDARDS.md)
- [Core 微內核架構手冊 (docs/core/README.md)](docs/core/README.md)
- [語意 URI 協議與動態解析手冊 (docs/core/uri_protocols.md)](docs/core/uri_protocols.md)
- [命名空間 Hook 與事件手冊 (docs/core/lifecycle_and_hooks.md)](docs/core/lifecycle_and_hooks.md)
- [Dev 開發者工具鏈手冊 (docs/dev/README.md)](docs/dev/README.md)
- [Dev 測試框架與沙盒指南 (docs/dev/testing_guide.md)](docs/dev/testing_guide.md)

---

## 📄 License
MIT License
