# 任務工作清單 (Task List)

> 功能名稱：Module 安裝期連動系統設計 (Installation-time Interlock System)  
> 建立日期：2026-08-23  
> 所屬主計畫：無  
> 依據實作計畫：[P04_implementation_plan.md](./P04_implementation_plan.md)  
> 狀態：Completed  
> 擴充項目：dogfooding_pipeline_ext  
> 模板版本：v1.2  

---

## 實作任務進度矩陣 (Implementation Matrix)

- [x] **Task 1: Core SDK 跨模組貢獻查詢通道**
  - [x] 1.1 在 `ys_codebase/source/core/scripts/context.py` 新增 `get_contributions(namespace: str)`
  - [x] 1.2 支援同時掃描 `modules/` 與 `source/` 下各模組的 `manifest.json`
  - [x] 1.3 實作安全寬容提取（非 dict 或缺失時略過不報錯）

- [x] **Task 2: Installer 批次完成後單次生命週期廣播**
  - [x] 2.1 在 `ys_codebase/yscb_installer.py` 的 `ModuleManager` 新增 `_broadcast_modules_changed(changes)`
  - [x] 2.2 於 `install()`, `pull()`, `remove()` 批次事務成功後調用一次
  - [x] 2.3 確保 `build()` 指令嚴格**排除**廣播調用
  - [x] 2.4 實作例外隔離防護（子進程調用、`timeout=30`、僅輸出 Warning 日誌）

- [x] **Task 3: SOP Slot 補丁動態合成引擎**
  - [x] 3.1 建立 `ys_codebase/source/agents-workflow/scripts/sop_synthesizer.py`
  - [x] 3.2 實作 `SOPSynthesizer.synthesize_sop()`（支援 `target_slot` 匹配與 `append`/`prepend` 注入）
  - [x] 3.3 實作 `SOPSynthesizer.strip_slot_markers()`（正則清除殘留 `YSCB_SLOT` 標記）

- [x] **Task 4: IDE 生成快取與孤兒檔案清理追蹤器**
  - [x] 4.1 建立 `ys_codebase/source/agents-workflow/scripts/ide_sync.py`
  - [x] 4.2 實作 `IDECacheTracker`（管理 `.yscb_cache/ide_workflow_manifest.json`）
  - [x] 4.3 實作 `clean_orphans()` 安全比對並清理廢棄指令檔案

- [x] **Task 5: 雙層 Extension 發現與優先級調度器**
  - [x] 5.1 建立 `ys_codebase/source/agents-workflow/scripts/ext_registry.py`
  - [x] 5.2 實作 `ExtensionRegistry.discover_all()`（聚合 `sop_ext://` 與 `contributes.sop_extensions`）
  - [x] 5.3 實作同名 Extension 優先級覆蓋（`sop_ext://` 優先）

- [x] **Task 6: 建立 `workflows/commands/` 基準庫並植入 Slot 標記**
  - [x] 6.1 建立 `ys_codebase/source/agents-workflow/workflows/commands/` 目錄
  - [x] 6.2 複製指令模板至 `commands/`，並於 `NewPlan.md` (Phase0~7)、`Review.md` (Step1~4)、`ContextInit.md` (Step1~4) 植入 `<!-- YSCB_SLOT:<SlotName> -->` 標記

- [x] **Task 7: `agents-workflow` 生命週期廣播 Hook**
  - [x] 7.1 建立 `ys_codebase/source/agents-workflow/scripts/_on_modules_changed.py`
  - [x] 7.2 解析 `action:module` CLI 傳參清單
  - [x] 7.3 執行 `commands/` ➔ `workflows/` 具體化合成輸出
  - [x] 7.4 偵測環境：若存在 `.agents/workflows/`，自動觸發 `ide_sync` 同步

- [x] **Task 8: 升級 `cli.py` 與 `verify_plan.py`**
  - [x] 8.1 升級 `generate_antigravity_ide_commands()` 串接 `SOPSynthesizer` 與 `IDECacheTracker`
  - [x] 8.2 升級 `ext list` 與 `ext show` 支援雙層來源標籤排版（`[sop_ext]` vs `[module: <name>]`）
  - [x] 8.3 升級 `verify_plan.py` 支援調度跨模組貢獻之驗證腳本

- [x] **Task 9: 建立標準 Mock 測試外掛模組**
  - [x] 9.1 建立 `test/fixtures/mock_workflow_plugin/` 目錄結構
  - [x] 9.2 建立 `manifest.json`（宣告 `contributes.agents-workflow` 含 patches 與 extensions）
  - [x] 9.3 建立範例 `templates/mock_rules.md` 與 `scripts/mock_verify.py`

- [x] **Task 10: 連動系統全量單元與整合測試**
  - [x] 10.1 建立 `test/test_interlock.py`
  - [x] 10.2 覆蓋 FT-01~08、ET-01~08、PT-01 等全量測試案例 (17/17 Passed)

- [x] **Task 11: Dogfooding 建置、回歸與同步**
  - [x] 11.1 更新 `test/test_interlock.py` 自動納入 `test/run_regression.py`
  - [x] 11.2 Stage 1 (Source) 驗證
  - [x] 11.3 Stage 2 (Build) 執行 `python yscb_cli.py installer build --all`
  - [x] 11.4 Stage 3 (Regression) 實機執行 `python test/run_regression.py` (53/53 Passed + E2E 100%)
  - [x] 11.5 Stage 4 (Sync) 覆蓋根目錄起手腳本、force install、重新生成 IDE 指令並核驗 `AGENTS.md`
