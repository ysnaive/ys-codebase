# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Agents-Workflow Release 預設 Local 模式、Gitignore 軟合併同步與 Core Config 來源層級探測 (Release Local Mode, Gitignore Sync & Core Config Origin Inspection)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_05)  
> 狀態：Confirmed  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：
  > agents-workflow release 添加並將 release 預設為 local 模式
  > 
  > # 問題概述:
  > 原有 release target 皆設定在 project 層級，這導致當多人協作時，並非所有人都用同一種開發工具，因而產出許多無用文檔，大多時候無害，但某些情況會汙染 knowledge-db 索引，和 Agents 大範圍檢索時的能力
  > 
  > # 預期方案:
  > 1. agents-workflow cli 相關啟用/停用 指令改為預設操作 local config，使用 --proj 改為 project 層級
  > 2. 自動於 project:// 中進行 ignore 區塊軟合併，或在不存在的情況下新建
  > 3. 為 core.config 擴充取得設定來源層級之能力 (`get_raw` / `inspect`)
- **核心目標**：
  1. **Core Config 來源層級探測 API**：為 `core.config` 增補 `get_raw(module, key=None, local=False, default=None)` 與 `inspect(module, key)`，可精確讀取單層原始組態並診斷來源層級（`local`, `project`, `both`, `none`）與覆蓋狀態。
  2. **Release Target 預設 Local 模式**：將 `agents-workflow` 的 release target 啟用/停用 (`release-target --add / --remove`) 操作預設寫入 **`config.local.json`**（Tier 1 本機私有組態，不入 Git），避免團隊協作時不同開發者使用不同 IDE 互相污染專案目錄。
  3. **支援 `--proj` 旗標**：提供 `--proj` / `--project` 旗標以支援顯式寫入 **`config.project.json`**（Tier 2 團隊共用組態）。
  4. **Target 來源辨識排版**：`release-target --list` 能夠清楚識別並標註 Target 的啟用來源（`[ENABLED (LOCAL)]`, `[ENABLED (PROJECT)]`, `[DISABLED]` 等）。
  5. **`project://.gitignore` 區塊非破壞性軟合併 (Soft-Merge)**：在 `ReleasePublisher.release_all()` 發布流水線中，自動於 `project://.gitignore` 進行 Target 忽略區塊之軟合併（若不存在則新建），確保本地產生的 Target 專屬目錄/檔案不會誤入 Git 倉庫。
- **邊界排除 (Explicitly Excluded)**：
  - 不變更現有 `ArtifactCompiler` 與 4 步原子發布交易的核心渲染邏輯。
  - 不硬性刪除用戶自訂的 `.gitignore` 外部規則。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[sub_05:P00:DR-01] Local 預設組態寫入與 --proj 旗標**：`ReleaseTargetManager.add_target()` 與 `remove_target()` 預設 `is_project=False`（寫入 `config.local.json`）；傳入 `--proj` 旗標時寫入 `config.project.json`。
- **[sub_05:P00:DR-02] 階層式 Target 解析與狀態辨識**：`ReleaseTargetManager.list_targets()` 同時檢查 Local 與 Project 組態，標註來源 `[ENABLED (LOCAL)]`、`[ENABLED (PROJECT)]` 或 `[DISABLED]`。`ReleasePublisher` 發布時讀取全域有效 Target 合集。
- **[sub_05:P00:DR-03] .gitignore 區塊軟合併機制 (Soft-Merge Ignore Block)**：
  - 定義專屬標記：
    ```gitignore
    # === YSCB AGENTS_WORKFLOW IGNORE BEGIN ===
    # Auto-managed by agents-workflow. Do not edit this block manually.
    <patterns...>
    # === YSCB AGENTS_WORKFLOW IGNORE END ===
    ```
  - 當發布 Target 時，提取所有啟用的 target 產物路徑或宣告之 ignore patterns，軟合併更新該區塊；區塊外的自訂規則保持 100% 完好無損。若 `.gitignore` 不存在則自動建立。
- **[sub_05:P00:DR-04] Core Config 來源層級探測能力擴充**：為 `core.config` 增補 `get_raw()` 與 `inspect()` API，提供微內核層級的組態來源溯源能力，支援各模組消費端精準診斷。

---

## 3. 開放議題與確認紀錄

- [x] **問題與方案對齊**：已確認預設 local 模式、--proj 旗標切換與 `.gitignore` 軟合併機制。
- [x] **Core Config 來源探測擴充確認**：已確認增補 `get_raw` 與 `inspect` API。
- [x] **Phase 0 討論定稿**：P00 標記為 Confirmed。
