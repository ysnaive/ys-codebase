# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：yscb_venv_core  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-06 在 P03 API 規格書中均有 1:1 映射之核心方法與類別
- [x] **邊界防護**：EC-01 ~ EC-06 在 `PipManager`、`IdeProjector` 與 `yscb.py` 均有具體防禦與跨平台路徑適配
- [x] **依賴純淨**：`core` 模組 100% 依賴 Python 原生標準庫，完全符合 NFR-01 ~ NFR-04 之指標約束

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **最高工程規範** | `docs/_project/STANDARDS.md` | Modify | 增補 `yscb.venv://` 空間協議，實體路徑指向 `yscb://.venv/`，Git 政策標記 `🚫 忽略` |
| **核心模組手冊** | `docs/core/README.md` | Modify | 補充 YSCB 私有微虛擬環境治理機制與 `PipManager`、`IdeProjector` 說明 |
| **專案歷史變更** | `CHANGELOG.md` | Modify | 記錄本次私有微環境隔離治理核心功能之完成摘要 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：若宿主環境缺少 `ensurepip` 或處於 Linux 精簡容器未安裝 `python3-venv`，系統是否會崩潰？  
> 💡 **防護解法**：`PipManager.ensure_venv` 預先檢查並捕獲 `subprocess.CalledProcessError` 或 `ModuleNotFoundError`，輸出清晰的環境安裝指引（例如提示 `apt-get install python3-venv`），阻斷崩潰並維持 `core` 模組原生功能可用。

> ❓ **尖銳問題 2**：若使用者本機 `.vscode/settings.json` 已有自訂的 `extraPaths` 與其他外掛設定，自動投影是否會造成覆寫破壞？  
> 💡 **防護解法**：`IdeProjector` 嚴格比照 `internal yscb gitignore` 哲學，在 `settings.json` 引入 `_yscb_managed` 宣告式清冊。每次更新僅依據舊清冊差集替換 YSCB 管轄項目，對使用者的全部自訂設定 100% 零干擾；若專案無 `.vscode` 目錄則靜默略過，零目錄污染。

> ❓ **尖銳問題 3**：`yscb.py` 啟動時動態探測微環境路徑，是否會拖慢 CLI 命令列極速分發？  
> 💡 **防護解法**：路徑探測採用純字串拼接與 `os.path.isdir` 檢查，單次探測耗時 $< 0.05\text{ms}$，且一旦加入 `sys.path` 即快取短路，對 sub-100ms 執行保證零可感延遲。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：更新基礎協議與忽略規則（`yscb.py` 注入 `/.venv/`、`STANDARDS.md`、`contributes/core.json`、`core/uri.py`）
- [ ] **TASK-02**：實作 `source/core/core/pip_manager.py`（`PipManager` 與 `PipInstallError`）
- [ ] **TASK-03**：實作 `source/core/core/ide_projector.py`（`IdeProjector` 與 `_yscb_managed` 可復原軟合併）
- [ ] **TASK-04**：宿主動態注入與還原管線對接（`yscb.py` 之 `_ensure_private_venv_path` 與 `cmd_restore`）
- [ ] **TASK-05**：安裝器對接（`source/core/core/installer.py` 解析 `pip_dependencies` 並物化）
- [ ] **TASK-06**：編寫單元測試套件 `source/core/tests/test_venv_core.py` 並實機執行回歸跑測
- [ ] **TASK-DOC**：更新 `docs/_project/STANDARDS.md` 與 `docs/core/README.md`

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全生態系協議統一性**：私有微環境命名統一為 `yscb.venv://`，映射至 `yscb://.venv/`，全生態系工具鏈對齊。
- **[P04:DR-02] 軟合併防護雙保險**：IDE 投影僅在 `project://.vscode` 存在時觸發，且必須附帶 `_yscb_managed` 宣告式清冊以支援 100% 精準復原。
