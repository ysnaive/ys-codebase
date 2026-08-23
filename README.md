# YS-Codebase (`ys-codebase`)

一套專為個人獨立開發者、中小型團隊與 Case-by-Case / 接案專案打造的輕量、模組化 AI Agent 代碼庫工程工具與規範管理系統。

---

## 🌟 核心架構特色

1. **100% 專案自包含 (Self-Contained)**：無任何機器/使用者全域環境污染，零外部第三方依賴（純 Python 3 標準庫實現）。
2. **2 × 2 設定與協定矩陣 (The 2x2 Matrix)**：
   - 範疇：`Codebase`（全專案基底） vs. `Module`（單一模組）
   - 權限與生命週期：`ProjectLevel`（`*.project.json`，進 Git 團隊規範） vs. `UserLevel`（`*.local.json`，忽略 Git 個人偏好）
3. **語意 URI 協定 (Semantic URI Protocol)**：提供 `project://`, `yscb://`, `plans://`, `archive://`, `docs://`, `sop_ext://` 虛擬協議，跨模組無障礙精準定錨。
4. **防侵入式軟合併 (Non-destructive Soft-Merge)**：`AGENTS.md` 與專案文檔透過定界標記 (`<!-- YSCB_AGENTS_BEGIN -->`) 進行自動局部同步，兼顧中央規範升級與專案特化規則保留。
5. **統一核心 Runtime SDK (`yscb_core`)**：提供全模組共享的 `ProjectContext`, `ConfigManager`, `Console`, `ProjectURI` 與 `!undefined` 未初始化安全攔截。
6. **自引用（Dogfooding）三層架構**：
   - **`:/ys_codebase/` [工具庫源碼環境]**：工具庫源碼（Installer、CLI、`source/` 源碼庫、`build/` 發布產物空間）。
   - **`:/test/` [假專案測試環境]**：模擬下游真實消費者專案，配置獨立沙盒與全自動回歸測試套件（`run_regression.py`）。
   - **`:/` [自引用 Dogfooding 環境]**：根專案自引用使用 `ys-codebase` 工具（包含 `modules/`、`docs/` 知識庫、`plans/` 計畫紀錄與 `AGENTS.md` 行為準則）。

---

## 📁 倉庫結構

```text
ys-codebase/ (專案根目錄，代表 "project://" / ":/"，自引用 Dogfooding 環境)
├── AGENTS.md                          # [AI 準則] 專案 AI Agent 行為規範入口 (含軟合併區塊)
├── README.md                          # [專案說明] 本文件
├── yscb_cli.py                        # [統一調度] 統一 CLI 轉接器
├── yscb_installer.py                  # [安裝引擎] 模組安裝、建置與套件管理
├── yscb_config.json                   # [Codebase.Project] 專案核心設定檔
├── yscb_config.template.json          # 純淨設定檔範本
│
├── .agents/                           # [IDE 整合] Google Antigravity / Gemini 工作流目錄
│   └── workflows/                     # 全量鏡像 + JIT 語意地圖之 Slash Command 工作流 (.md)
│
├── docs/                              # [知識庫] 專案系統知識庫 (docs://，1:1 鏡像結構)
├── plans/                             # [進行中計畫] 活躍開發計畫目錄 (plans://)
├── archive_plans/                     # [歷史計畫] 已封存歷史計畫目錄 (archive://)
├── extensions/                        # [SOP 擴充] 專案特化 SOP 擴充清單 (sop_ext://)
│
├── modules/                           # [自引用運行空間] 專案安裝之模組發布產物
│   ├── core/                          # 核心基座 SDK (yscb_core)
│   └── agents-workflow/               # AI Agent SOP 工作流模組實例
│
├── ys_codebase/                       # [工具庫源碼開發環境 (":/ys_codebase/")]
│   ├── yscb_cli.py                    # 源碼區 CLI 調度器
│   ├── yscb_installer.py              # 源碼區安裝管理引擎
│   ├── source/                        # [源碼空間] 模組完整源碼
│   │   ├── core/                      # 核心基座 (yscb_core SDK)
│   │   └── agents-workflow/           # AI Agent SOP 工作流模組源碼
│   └── build/                         # [發布產物空間] 封裝打包產物 (供下游消費)
│       ├── core/                      # Core SDK 發布物
│       └── agents-workflow/           # 由 source/ 打包產出之標準模組包
│
└── test/                              # [假專案測試環境 (":/test/")]
    ├── test_installer.py              # Installer 與 Core SDK 單元/整合測試套件
    ├── test_hardening.py              # 擴充性與可靠性強化回歸測試套件
    └── run_regression.py              # 一鍵全自動回歸測試腳本 (含沙盒 E2E 回歸，CI 同步執行)
```

---

## 🚀 下游專案標準起手式 (Project Setup Guide)

新專案欲導入 `ys-codebase` 時，請依下列 7 個步驟執行初始化：

### 步驟 1：建立專案工作目錄骨架
在專案根目錄建立工作目錄：
```bash
mkdir plans archive_plans extensions docs
```
*(建議於 `.vscode/settings.json` 中將 `.gitkeep`, `**/__pycache__` 等輔助檔案加入 `files.exclude`)*

### 步驟 2：獲取工具庫起手腳本
從 GitHub 下載 `yscb_installer.py` 與 `yscb_cli.py` 至專案根目錄：
```bash
curl -O https://raw.githubusercontent.com/YsNaive/ys-codebase/main/ys_codebase/yscb_installer.py
curl -O https://raw.githubusercontent.com/YsNaive/ys-codebase/main/ys_codebase/yscb_cli.py
```

### 步驟 3：初始化工具庫全域設定
在專案根目錄執行：
```bash
python yscb_installer.py init -p .
```
這將生成專案層級的 `yscb_config.json`，將專案根目錄與工具庫目錄正確錨定。

### 步驟 4：安裝 AI 工作流模組
執行安裝指令（安裝器會自動解析相依並安裝 `core` SDK 基座）：
```bash
python yscb_cli.py installer install agents-workflow
```

### 步驟 5：執行模組路徑初始化與 `AGENTS.md` 建立
```bash
# 推薦預設快速初始化 (自動在根目錄建立 AGENTS.md 軟合併標準檔):
python yscb_cli.py agents-workflow init --default

# 或使用嚴格語意 URI 顯式個別指定:
python yscb_cli.py agents-workflow init \
  --plans-dir project://plans \
  --archive-dir project://archive_plans \
  --docs-dir project://docs \
  --extensions-dir project://extensions \
  --agents-md project://AGENTS.md
```

### 步驟 6：生成 Google Antigravity / Gemini IDE 引用式指令
```bash
python yscb_cli.py agents-workflow --ide-antigravity
```
這將在 `.agents/workflows/` 生成 8 大標準 Slash Command（含 JIT 專案語意解析地圖與完整 SOP 步驟）。

### 步驟 7：全鏈路健康度驗證
```bash
# 1. 驗證 6 大語意協議矩陣狀態 (應全數為 [ACTIVE])
python yscb_cli.py uri list

# 2. 稽核系統知識庫死鏈與 Frontmatter
python yscb_cli.py agents-workflow docs audit
```

---

## 🧭 Codebase 語意 URI 協定 (Semantic URI Protocol)

本專案支援語意 URI 協定，避免跨層級呼叫時脆弱的相對路徑跳轉：

| 語意 URI 協議 | 核心語意 | 說明 |
| :--- | :--- | :--- |
| **`project://<path>`** | 專案最頂層根目錄 | 指向專案根目錄（例：`project://AGENTS.md`） |
| **`yscb://<path>`** | 工具庫管理根目錄 | 指向工具庫源碼或安裝目錄（例：`yscb://source/core`） |
| **`plans://<path>`** | 活躍開發計畫目錄 | 指向進行中 Dev Plan 目錄（由 `paths.plans_dir` 定義） |
| **`archive://<path>`** | 歷史封存計畫目錄 | 指向歷史歸檔目錄（由 `paths.archive_dir` 定義） |
| **`docs://<path>`** | 系統知識庫目錄 | 指向專案知識庫目錄（由 `paths.docs_dir` 定義） |
| **`sop_ext://<path>`** | 專案 SOP 擴充目錄 | 指向專案特化擴充清單目錄（由 `paths.extensions_dir` 定義） |

> 💡 **開放註冊協定**：任何模組皆可於 `manifest.json` 宣告 `contributes["core"]["uri_schemes"]` 註冊自訂協議（例：`{"scheme": "notes", "config_key": "notes_dir"}`），無須修改 core SDK。`project://` 與 `yscb://` 為保留字。

### 🛠️ URI 終端動態解析指令
```bash
# 解析語意 URI 為實體絕對路徑
python yscb_cli.py uri resolve docs://_project/STANDARDS.md

# 列出所有已註冊協議與當前解析狀態
python yscb_cli.py uri list

# 將本機實體路徑轉換為語意 URI
python yscb_cli.py uri to-uri docs/_project/STANDARDS.md
```

---

## 🛠️ 模組常用指令速查 (CLI Cheat Sheet)

### 1. 安裝器管理 (`installer`)
```bash
python yscb_cli.py installer status               # 檢視已安裝模組、版本與實體狀態報告
python yscb_cli.py installer update --all         # 更新全量模組至最新發布物 (同 pull)
python yscb_cli.py installer remove <module_name> # 安全解除安裝指定模組 (同 uninstall，具真實相依防護)
python yscb_cli.py installer rollback <module> --list  # 列出模組可用快照備份
python yscb_cli.py installer rollback <module>    # 一鍵還原模組至升級前快照
python yscb_cli.py installer self-update          # 升級 installer 與 CLI 起手腳本
```

### 2. 工作流定式作業 (`agents-workflow`)
```bash
python yscb_cli.py agents-workflow verify         # 稽核 Dev Plan 階段合規性與 Extension
python yscb_cli.py agents-workflow scan --all     # 掃描專案開發計畫狀態矩陣 (含歷史歸檔)
python yscb_cli.py agents-workflow search -q "DB" # 檢索歷史計畫與 DR 決策記錄
python yscb_cli.py agents-workflow archive <plan> # 安全歸檔已完成之計畫目錄
python yscb_cli.py agents-workflow ext list       # 查詢專案可用之 SOP Extension 擴充清單
```

### 3. 知識庫守護工具 (`docs`)
```bash
python yscb_cli.py agents-workflow docs init      # 初始化知識庫全域地圖骨架
python yscb_cli.py agents-workflow docs audit     # 檢查 docs/ 內部相對路徑死鏈與語法
python yscb_cli.py agents-workflow docs new-topic <Module> <topic> # 快速生成專題技術手冊
```

---

## 🔄 工具庫開發者維護工作流 (For Maintainers)

```bash
# 1. 於 ys_codebase/ 進行源碼修改後執行封裝建置
python yscb_installer.py build --all

# 2. 執行全量單元測試與下游端到端沙盒回歸驗證
python test/run_regression.py

# 3. 驗證通過後套用至根目錄自引用空間
python yscb_cli.py installer install agents-workflow --force
```

---

## 📄 License
MIT License
