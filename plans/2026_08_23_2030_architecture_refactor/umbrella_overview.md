# 分類型主計畫總覽 (Umbrella Plan Overview)

> 功能名稱：模組化體系宏觀架構重構與微內核遷移 (Module Architecture Specification & Microkernel Refactor)  
> 建立日期：2026-08-24  
> 所屬主計畫：無  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 狀態：Planning  
> 擴充項目：none  
> 模板版本：v1.2  

---

## 1. 目標說明與架構總綱

本 Umbrella 主計畫統籌 YS-Codebase 從「巨型單檔自引用體系」向「超薄宿主 (Ultra-Thin Host) + 微內核 (module:core) + 開發者套件 (module:dev) + 自治模組生態」之全方位宏觀架構重構與平穩遷移。透過 9 個細化子計畫，實現環境隔離、原生自舉、微內核套件管理、開發者工具鏈、自部署閉環、雙空間文檔更新與歷史業務模組 (`agents-workflow`) 的規範化適配。

---

## 2. 子計畫拆分清單與執行進度

| 編號 | 子計畫目錄名稱 | 預設 Track | 當前狀態 | 核心目標摘要 |
| :--- | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_quarantine_and_backup` | Fast Track | **已完成** | 處理現有檔案狀況：隔離現有模組至 `.quarantine/` 並備份歷史起手腳本與組態 |
| **sub_02** | `sub_02_host_bootstrapper` | Full Track | **已完成** | 建立宿主單檔：100% 原生實現超薄 `yscb.py`（含 `init`, `self-update`, CLI 轉接派發） |
| **sub_03** | `sub_03_core_module` | Full Track | **已完成** | 建立 `module:core`：實作 12 大原子操作、7 大 Installer 指令、語意 URI 與 Contributes 聚合器 |
| **sub_04** | `sub_04_dev_module` | Full Track | **已完成** | 建立 `module:dev`：實作模組腳手架 `create`、規範檢查 `check`、純淨打包 `build` 工具 |
| **sub_05** | `sub_05_dev_testing_workflow` | Full Track | **已完成** | 建立並完善 dev 測試流程：實作 `dev test` 沙盒測試引擎與標準化回歸測試矩陣 |
| **sub_06** | `sub_06_misc_polish_and_tests` | Full Track | **已完成** | 雜項功能完善補齊與 core, dev 標準化測試添加：補齊 Gap 1~5 核心機制並建立 8 大持久化標準測試套件 |
| **sub_07** | `sub_07_core_docs_update` | Fast Track | 未開始 | 文檔更新：更新專案根目錄、`core` 與 `dev` 模組之規範文檔與 README |
| **sub_08** | `sub_08_agents_workflow_migration` | Full Track | 未開始 | agents-workflow 模組遷移：依新架構規範重構 `agents-workflow` 並發布安裝 |
| **sub_09** | `sub_09_agents_workflow_docs_update` | Fast Track | 未開始 | agents-workflow 文檔更新：更新工作流 SOP 模板、URI 引導與行為準則文檔 |

---

## 3. 跨子計畫依賴關係圖 (Dependency Roadmap)

```mermaid
flowchart TD
    sub_01["sub_01: 處理現有檔案狀況<br/>(Quarantine & Backup)"] --> sub_02["sub_02: 建立宿主單檔<br/>(yscb.py Bootstrapper)"]
    sub_02 --> sub_03["sub_03: 建立 module:core<br/>(微內核與語意 URI)"]
    sub_03 --> sub_04["sub_04: 建立 module:dev<br/>(開發者建置工具)"]
    sub_04 --> sub_05["sub_05: 完善 dev 測試流程<br/>(沙盒測試引擎)"]
    sub_05 --> sub_06["sub_06: 驗證自部署與混合模式<br/>(Dogfooding 閉環驗證)"]
    sub_06 --> sub_07["sub_07: 核心與工具文檔更新<br/>(Host/Core/Dev Docs)"]
    sub_07 --> sub_08["sub_08: agents-workflow 模組遷移<br/>(SOP 模組化適配)"]
    sub_08 --> sub_09["sub_09: agents-workflow 文檔更新<br/>(SOP 與準則文檔發布)"]
```

---

## 4. 全域 Decision Records (Master DR)

### [UMBRELLA:DR-01] 微內核與超薄宿主職責分離
- **議題**：宿主 `yscb.py` 與套件管理、路徑處理功能耦合過重，單檔膨脹且難以自我升級。
- **結論**：`yscb.py` 縮減為百餘行超薄宿主（僅保留 `init`、`self-update` 與泛用 CLI 派發）；所有套件管理指令（7 項）與語意 URI 系統全數交由 `core` 模組自治實現。
- **理由**：實現 100% 零依賴自舉逃生艙，將業務複雜度完全模組化。
- **影響的子計畫**：`sub_02`, `sub_03`

### [UMBRELLA:DR-02] 語意空間協議與路徑封裝鐵律
- **議題**：模組直接存取底層路徑造成自引用死鎖與路徑混亂。
- **結論**：建立語意 URI 協議空間（`project://`, `yscb://`, `mirror://`, `temp://`, `snapshot://`, `cache://`, `config://`, `module://` 等），`ExecutionContext` 僅提供語意資訊（`module_name`, `command`, `args`），嚴禁暴露底層實體路徑。
- **理由**：保障模組自治與跨環境路徑確定性。
- **影響的子計畫**：`sub_03`, `sub_04`, `sub_08`

### [UMBRELLA:DR-03] 純淨產物版本化拓撲與 Provider 抽象
- **議題**：產物與源碼混雜，缺少版本管理與統一的套件倉庫來源抽象。
- **結論**：移除 `latest/` 實體目錄，產物空間與 Provider 統一遵循 `module.build.root://<module>/<version>/` 結構，透過 `index.json` 進行版本清冊發現與 SemVer 求解。
- **理由**：確保安裝產物 100% 純淨無開發污染，支援離線回滾與多版本管理。
- **影響的子計畫**：`sub_03`, `sub_04`, `sub_06`

### [UMBRELLA:DR-04] RELOAD 兩階段純淨物化與依賴注入保證
- **議題**：重載運行端時若採增量補丁易受前次注入髒狀態污染。
- **結論**：`RELOAD` 定案為「階段一：自鏡像全量覆蓋純淨 build 檔案 ➔ 階段二：掃描 5 大來源聚合 contributes 執行注入與廣播」兩階段管線。
- **理由**：確保運行端永遠維持在可預期的 100% 純淨初始狀態。
- **影響的子計畫**：`sub_03`, `sub_05`, `sub_06`

### [UMBRELLA:DR-05] 隔離式漸進遷移路線圖
- **議題**：重構期間避免舊版工作流與代碼干擾核心自舉構建。
- **結論**：現有代碼於 `sub_01` 移入 `.quarantine/` 隔離；待 `core`、`dev` 及自部署驗證閉環完成後，再於 `sub_08` 啟動 `agents-workflow` 的模組化遷移與回歸。
- **理由**：降低單次重構風險，確保每一步驟皆可實機驗證。
- **影響的子計畫**：`sub_01`, `sub_08`, `sub_09`
