# YS-Codebase (`ys-codebase`)

一套專為個人獨立開發者、中小型團隊與 Case-by-Case / 接案專案打造的輕量、模組化 AI Agent 代碼庫工程工具與管理系統。

---

## 🌟 核心架構特色

1. **極簡單檔起手**：下游專案僅需 checkout [`yscb_installer.py`](./yscb_installer.py) 與同層 [`yscb_config.json`](./yscb_config.json) 即可運作。
2. **Zero External Dependency**：純 Python 3 標準庫實現，跨平台（Windows / macOS / Linux）免安裝額外套件。
3. **Source / Build 雙軌分流**：
   - **標準使用者模式 (Build Mode)**：安裝 `build/<module>` 最終輸出工具與發布物。
   - **開發者源碼模式 (Source Mode, `--source`)**：安裝 `source/<module>` 原始碼，並**自動強制相依安裝 `source/core` 基礎庫**，解鎖本地 Modify、Build 與 Push 能力。
4. **模組生命週期管理**：完整支援 `help`、`init`、`install`、`pull`、`build`、`push`、`status`、`list`、`remove`。

---

## 📁 倉庫結構

```text
ys-codebase/
├── yscb_installer.py              # 核心安裝管理工具 (單一入口 CLI)
├── yscb_config.json               # 專案核心設定檔
├── README.md                      # 專案說明
│
├── source/                        # 原始碼空間 (開發者模式)
│   ├── core/                      # 核心基座 (任何 --source 模組的強制相依底層)
│   │   └── manifest.json
│   └── <module_name>/             # 各模組原始碼
│
├── build/                         # 發布產出物空間 (一般使用者安裝目標)
│   └── <module_name>/             # 編譯/封裝後的終端發布產物
│
└── tests/                         # 自動化測試套件
    └── test_installer.py
```

---

## 🚀 快速上手 (Quick Start)

### 1. 初始化專案配置
```bash
python yscb_installer.py init
```

### 2. 檢視可用模組
```bash
python yscb_installer.py list
```

### 3. 安裝模組
```bash
# 標準發布物模式安裝
python yscb_installer.py install <module_name>

# 開發者源碼模式安裝 (自動連帶安裝 source/core)
python yscb_installer.py install <module_name> --source
```

### 4. 檢視安裝狀態
```bash
python yscb_installer.py status
```

### 5. 說明文檔與手冊
```bash
# 完整指令總覽
python yscb_installer.py help

# 特定子指令手冊
python yscb_installer.py help install
```

---

## 📄 License
MIT License
