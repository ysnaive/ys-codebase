# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：modules_git_decoupling  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-05 在架構 (P02) 與 API 規格 (P03) 中均有 1:1 對應介面。
- [x] **邊界防護**：EC-01 ~ EC-05 均已設計對應之保護行為（空清冊防護、提取失敗降級、Clean 快速短路）。
- [x] **依賴純淨**：NFR-01 (JIT 耗時 $\le 2\text{ms}$)、NFR-02 (零第三方依賴)、NFR-03 (測試覆蓋率 100%) 符合量化指標約束。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **全域規範** | `docs/_project/STANDARDS.md` | Modify | 空間協議表：`module.root://` 與 `module://` 改為 `yscb://.modules/`，Git 政策標記為 `🚫 忽略`。 |
| **模組手冊** | `docs/core/README.md` | Modify | 補充運行端目錄變更為 `.modules/`、冷啟動 `restore` 指令與 JIT 自動同步自愈說明。 |
| **源碼手冊** | `ys_codebase/source/core/README.md` | Modify | 同步運行端空間協議與內部 API 說明。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1：全新 Clone 倉庫時，.modules/core 尚未物化，JIT 守門如何能在不依賴 core 的情況下自愈？**  
> 💡 **防護解法**：JIT 守門與模組提取解壓函式自包含於宿主腳本 `yscb.py` 內，僅使用 Python 原生標準庫（`os`, `json`, `zipfile`, `urllib`）。在 `main()` 調度任何指令前，JIT 守門優先自本地 provider 或 release 提取 `core` 及其他模組物化至 `.modules/`，隨後調用同進程 `reload`，完全不依賴已物化的模組即可達成冷啟動自愈。

> ❓ **尖銳問題 2：若開發者 A 升級了模組並提交 yscb.config.json，開發者 B git pull 後執行任意指令會發生什麼？**  
> 💡 **防護解法**：開發者 B 執行任何 CLI 指令時，`_ensure_jit_modules_sync` 在 $< 2\text{ms}$ 內偵測到 `yscb.config.json` 宣告之版本與本地 `.modules/<name>/manifest.json` 不一致（Dirty），立即觸發自動原地 JIT Restore，將對應版本模組覆蓋還原至 `.modules/` 並 reload，開發者 B 無需手動下達任何維護指令即可無感同步。

> ❓ **尖銳問題 3：自動生成 yscb://.gitignore 是否會干擾或污染專案根目錄的 .gitignore？**  
> 💡 **防護解法**：`_generate_internal_gitignore` 嚴格僅在 `yscb_abs`（即 `ys_codebase/.gitignore`）維護內部忽略清單，絕對禁止修改專案根目錄的 `.gitignore`，落實零外溢與自主沙盒邊界。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01**：`yscb.py` 內部 Git 忽略生成器更新，加入 `/.modules/` 條目 (FR-01)。
- [ ] **TASK-02**：`yscb.py` 運行端路徑全面由 `modules` 切換為 `.modules` (FR-02)。
- [ ] **TASK-03**：`yscb.py` 實作四階模組提取函式 `_restore_module_package` 與 `cmd_restore` (FR-03)。
- [ ] **TASK-04**：`yscb.py` 實作極速 JIT 模組同步守門 `_is_modules_dirty` 與 `_ensure_jit_modules_sync` (FR-04)。
- [ ] **TASK-05**：`core` 模組 `contributes/core.json` 與 `core/uri.py` 空間協議預設值對齊為 `yscb://.modules/` (FR-02)。
- [ ] **TASK-06**：編寫單元測試套件 `source/core/tests/test_restore_and_jit_modules.py`，覆蓋 FT-01~FT-04 與 ET-01~ET-02。
- [ ] **TASK-07**：文檔交付：修訂 `docs/_project/STANDARDS.md`、`docs/core/README.md` 與 `source/core/README.md` (FR-05)。
- [ ] **TASK-08**：Dogfooding 閉環驗證：執行 `dev test core --sync` 直裝驗證，並執行全生態系回歸測試 (NFR-03)。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 剛性鎖定 8 步實作拓撲與 JIT 零感自愈**：
  - 嚴格依照 TASK-01 ~ TASK-08 拓撲順序進行編碼，確保單一原子提交、100% 測試覆蓋與文檔同步交付。
