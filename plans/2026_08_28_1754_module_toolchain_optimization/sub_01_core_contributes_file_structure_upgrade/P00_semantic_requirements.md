# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Core Contributes 系統檔案結構升級 (Core Contributes File Structure Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_01)  
> 狀態：Confirmed  
> 計畫類型：Refactor / Architecture  
> 模板版本：v1.1  


---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：開起子計畫01，core contributes 之系統檔案結構升級，先調研現有之 contributes 系統架構與細節。1. 還未規模投入使用，本次遷移不進行舊版本相容。2. 恪守三層空間邊界，運行端一律透過 `install @build` 或沙盒部署，絕對禁止探知 `module.source://`。
- **核心目標**：
  1. 完成現有 `contributes` 系統架構與消費端調用細節調研（已於 `R01` 交付）。
  2. 確立**「無歷史包袱之純淨檔案結構遷移」**：徹底廢除 `manifest.json` 內嵌貢獻與根目錄散落檔案，全面採用 `source/<module>/contributes/<target>.json`（唯一官方標準）。
  3. **恪守三層空間公理與反模式清理**：徹底清除 `compiler.py` 與 `providers.py` 遺留之 `module.source://` 穿透代碼，運行端嚴格僅讀取 `module://`。
  4. **全域消費端統一收斂**：將 `core/providers.py`、`core/engine.py`、`knowledge-db/space.py`、`agents-workflow/compiler.py` 手寫掃描邏輯 100% 廢除，全面收斂為標準 `core.contributes.get()`。
- **邊界排除 (Explicitly Excluded)**：
  - 嚴禁在運行端增加任何探知 `module.source://` 的邏輯。
  - 不保留舊版相容代碼（不支援 Manifest 內嵌 contributes 與根目錄 `contributes.<target>.json`）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[sub_01:P00:DR-01] 開立子計畫 sub_01**：開立子計畫目錄 `plans://2026_08_28_1754_module_toolchain_optimization/sub_01_core_contributes_file_structure_upgrade/`。
- **[sub_01:P00:DR-02] 交付 R01 專題架構調研報告**：確立現行架構全景、資料流、4 大模組清冊與消費端手寫 Fallback 之根因。
- **[sub_01:P00:DR-03] 確立純淨無歷史包袱遷移 (Breaking Pure Refactor)**：開發者確認不保留向下相容，採用單一權威標準 `contributes/<target>.json`，Manifest 全面瘦身。
- **[sub_01:P00:DR-04] 恪守三層空間公理與消費端全面收斂**：明確運行端嚴格僅讀取 `module://`，清理所有 `module.source://` 穿透壞味道，全模組消費端強制統一調用 `core.contributes.get()`。
- **[sub_01:P00:DR-05] 專案級 config 空間特化注入**：聚合引擎重構依然完整保留對 `config://` 空間之掃描，允許下游專案透過 `config.project.json` / `config.local.json` 進行專案特化擴充與覆蓋。


---

## 3. 開放議題與確認紀錄

- [x] **確認 1 (調研結論覆核)**：R01 調研已清楚揭示消費端手寫邏輯為歷史穿透壞味道。
- [x] **確認 2 (純淨無相容遷移路線)**：開發者確認不進行舊版本相容，全系統直上純淨目錄化結構 `contributes/<target>.json`。
- [x] **確認 3 (三層空間隔離公理)**：確立運行期模組絕對不探知 `module.source://`，維持 `module://` 純淨邊界。
- [ ] **確認 4 (P00 定稿與推進 Phase 1)**：等待開發者確認定稿 P00（標記為 `Confirmed`）並指示推進至 Phase 1。


