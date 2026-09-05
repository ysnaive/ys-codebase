# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：yscb_venv_core  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  - 「進入 sub_04_yscb_venv_core ，R02 所述之零全域污染、開箱即用+Python 原生雙軌平穩降級兜底僅限於 "core" 核心模組，本次計畫完成後，後續模組可自由進行 pip 依賴」
  - 「P00:DR-02 新增協議，名稱定為 "yscb.venv://" = "yscb://.venv/"」
  - 「FR-06 修改方案，改為在安裝模組時自動感知並進行軟合併，自動檢測 project://.vscode 是否存在」
  - 「補充: 需用類似 internal yscb gitignore 這種明確標示，可復原之軟合併」
- **核心目標**：
  - 依據 [R02 調研報告](file:///workspace/ys-codebase/plans/2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance/R02_pip_dependency_governance_and_optional_acceleration.md) Stage 1 & Stage 2，落實 YSCB 私有 Pip 微環境治理核心設施：
    1. **私有微環境隔離空間 (`core.pip_manager`)**：建立 `yscb.venv://`（即 `yscb://.venv/`）空間協議，支援依 Python 版本（`py{major}{minor}`）分層管理私有隔離環境與 `site-packages`。
    2. **Wheel-Only 靜默安裝**：`core.installer` 解析模組 `manifest.json` 之 `pip_dependencies` 宣告，並透過私有 Pip 隔離管理器安全安裝，徹底避免本機全域環境污染與 PEP 668 鎖定。
    3. **宿主啟動動態注入**：`yscb.py` 同進程分發與啟動時，動態嗅探當前 Python 版本對應之私有微環境 `site-packages` 並安全注入 `sys.path`。
    4. **冷啟動再生對齊**：`python yscb.py restore` 自動依已安裝模組清冊恢復並重建物化私有 Pip 依賴。
    5. **空間協議與 Git 追蹤政策**：於 `docs/_project/STANDARDS.md`、`core` 空間解析器與 `yscb://.gitignore` 注入 `yscb.venv://` 空間協議，標記為 `🚫 忽略`。
    6. **模組安裝自動感知與具明確標示之可復原 IDE 軟合併**：於模組安裝/更新/還原時自動檢測 `project://.vscode` 是否存在；若存在，採用類似 internal yscb gitignore 的明確標示機制（如 `_yscb_managed` 宣告式結構）進行非破壞性且可完全復原之軟合併，增量更新 `extraPaths` 與 `defaultInterpreterPath`；若不存在則靜默略過，不強行生成目錄。
- **邊界排除 (Explicitly Excluded)**：
  - **業務模組代碼遷移與硬體加速改寫**：如 `knowledge-db` 導入 `zstandard`/`lmdb`/`tree-sitter` 等實作，排除於本次子計畫，留待 `sub_05_modules_migration_and_optimization` 專項推進。
  - **沙盒高級回收機制**：暫不實作跨環境 Wheel 快取垃圾回收 (`--gc`) 等次要功能。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01] 私有微環境隔離與降級邊界定性**：
  - **決策**：「零全域污染、開箱即用、純 Python 原生標準庫雙軌平穩降級」之嚴苛約束**僅限於 `core` 核心模組**。
  - **依據**：`core` 模組身為微內核與冷啟動引導器，必須具備 100% 零依賴開箱即用能力；但生態系其餘業務模組在本次 `sub_04` 私有環境基礎設施就緒後，可自由宣告與使用 pip 依賴，無須強制實作繁複的純 Python 降級兜底。
- **[P00:DR-02] 空間協議與 Git 忽略策略**：
  - **決策**：正式引入 `yscb.venv://` 語意空間協議，實體路徑指向 `yscb://.venv/`（即 `ys_codebase/.venv/`）。
  - **依據**：對齊 `STANDARDS.md` 前綴點號隱藏目錄規範（與 `.modules/`、`.build/` 一致）與點號命名風格，並於 `yscb://.gitignore` 的內部維護標記區塊內自動軟合併注入 `/.venv/`，確保私有微環境 100% 不入庫。
- **[P00:DR-03] 宿主啟動動態注入架構 (`sys.path`)**：
  - **決策**：在 `yscb.py` 入口前置注入邏輯，檢測當前 Python 運行版本之 `ys_codebase/.venv/py{major}{minor}/lib/python{major}.{minor}/site-packages`（或 Windows 對應路徑），動態插入 `sys.path`。
  - **依據**：消除全域 `PYTHONPATH` 污染，模組在被調度運行時即可直接無感 `import` 私有依賴。
- **[P00:DR-04] `manifest.json` 宣告與靜默安裝規範**：
  - **決策**：模組於 `manifest.json` 透過 `"pip_dependencies": { "package": ">=version" }` 宣告依賴。
  - **依據**：`core.installer` 於 `install` / `update` / `restore` 階段收集依賴聯集，調用私有隔離環境之 pip 執行 `--only-binary=:all:` 安裝，若遇到無 binary wheel 則進行友善提示。
- **[P00:DR-05] 模組安裝自動感知與具明確標示之可復原 IDE 軟合併**：
  - **決策**：在模組安裝/更新/還原 (`install` / `update` / `restore`) 流程完成後，自動探測 `project://.vscode` 目錄是否存在。若存在，比照 `internal yscb gitignore` 之標記守門哲學，採用**具備明確標示之可復原軟合併演算法**（透過 `_yscb_managed` 宣告式專屬結構精確管理 YSCB 注入之 `extraPaths` 與 `defaultInterpreterPath`），既可精準增量更新、比對去重，亦可隨模組移除或還原時 100% 無損乾淨回滾，絕不污染使用者既有自訂設定。若目錄不存在則完全靜默略過。
  - **依據**：對齊專案整體防護與可追溯紀律，兼顧自動感知、零目錄污染與雙向可復原性。

---

## 3. 開放議題與確認紀錄

- [x] 是否已明確 `core` 與其餘模組之邊界責任劃分？（已確認：僅 `core` 限制純原生雙軌降級，其餘模組在 `sub_04` 完成後可自由進行 pip 依賴）。
- [x] 本子計畫是否僅專注於微環境核心基礎設施與 IDE 自動感知投影？（已確認：`sub_04` 專注於 Stage 1 & 2，各業務模組遷移留待 `sub_05`）。
