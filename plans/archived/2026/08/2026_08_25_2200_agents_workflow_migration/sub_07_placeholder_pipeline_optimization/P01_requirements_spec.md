# 需求規格說明書 (Phase 1: Requirements Specification)

> 功能名稱：佔位符解析管線優化 (Placeholder Pipeline Optimization)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 核心行為描述 | 預期輸出 / 驗收標準 | 對應 P00 語意 |
| :---: | :--- | :--- | :--- | :--- |
| **FR-01** | 快取中繼與 exports 廢棄 | 刪除原 `module.root://agents-workflow/exports` 目錄；Stage 1 專注解算 `__@{token}__`，中繼產物物化寫入 `cache.root://agents-workflow/resolved_contents/`。 | 模組安裝/源碼目錄不再殘留 `exports/`，快取目錄產出結構純淨之 standards/workflows/templates 中繼檔案。 | P00 § 2 (階段 2) |
| **FR-02** | `release_target` Contributes 規格 | 在 `manifest.json` 支援 `release_target` 宣告，包含 `projections`（`target_dir`, `extension`, `header: str \| list`），支援 `{export.description}` 等巨集插值。 | 成功解析 `release_target` 宣告，並支援純文字/陣列 Header 巨集插值渲染。 | P00 § 2 (階段 3) |
| **FR-03** | `config.project.json` 組態重構 | 移除原 `"ide": []`，改用 `"release_targets": []`；保留 `enable_agents_md` 與 `enable_project_changelog` 原生開關。 | 組態檔成功持久化啟用之 Target 名稱清單與原生特化開關。 | P00 § 2 (階段 3) |
| **FR-04** | 三層 URI 重映射與相對路徑計算 | Stage 2 讀取中繼產物，依三層階層（Tier 1 Target Exports 拓撲表 ➔ Tier 2 Core 專案協議 ➔ Tier 3 兜底）將 `__#{uri}__` 動態計算為本機實體相對路徑（`os.path.relpath`）。 | 目標產物中的 `__#{uri}__` 成功轉譯為如 `../templates/P00.md`、`../../AGENTS.md` 之本機相對路徑，且路徑分隔符統一為 `/`。 | P00 § 2 (階段 4) |
| **FR-05** | 原子 4 步 `release` 交易機制 | 實作過往清理 ➔ 提前解算 ➔ 持久清單 (`storage://agents-workflow/release_manifest.json`) ➔ 目錄建立與落地產出（含 `AGENTS.md` 軟合併）。 | 具備 Transactional Atomic 特性，徹底消除殘留孤立檔案與中途崩潰檔案損毀風險。 | P00 § 2 (階段 5) |
| **FR-06** | CLI 指令體系實裝 | 實作 `release`（全量已啟用發布）、`release-target --list`（狀態/孤立標註）、`release-target --add <t>`（啟用並發布）、`release-target --remove <t>`（停用並清理）。 | 終端指令互動順暢，add/remove 自動觸發 release 閉環。 | P00 § 3 (CLI 規範) |
| **FR-07** | 核心資產路徑引用全面更新 | 將 `assets/` 內部所有 standards、workflows、templates 中的路徑引用全面遷移為 `__#{uri}__` 語意標籤。 | 所有核心資產無寫死相對路徑，完全依循語意解耦標準。 | P00 § 4 (範疇邊界) |

---

## 2. 邊界條件與例外處理 (Edge Cases & Exception Handling)

| 邊界編號 | 情境描述 | 期望系統防禦行為 | 對應需求 |
| :---: | :--- | :--- | :---: |
| **EC-01** | 配置了未註冊之 Target (Orphan Target) | `release-target --list` 標註 `[ORPHAN / NOT FOUND]`；發布時跳過該 Target 並發出 Warning，不影響其他合法 Target。 | FR-02, FR-06 |
| **EC-02** | `__#{uri}__` 指向無法解析之未知協議 | 安全降級為純文字路徑，在終端輸出 `[compiler:warning]`，流水線絕不崩潰。 | FR-04 |
| **EC-03** | 提前解算發布清單時發生例外 | 立即中止發布交易，不修改 `release_manifest.json`，不污染專案實體檔案系統。 | FR-05 |
| **EC-04** | Header 巨集插值缺失欄位 (KeyError) | 自動安全回退為空字串 `""` 或 `{export.name}`，保證格式生成平滑。 | FR-02 |
| **EC-05** | 過往發布之檔案已遭手動刪除 | 清理階段捕捉 `FileNotFoundError` 並安全略過，不影響後續流程。 | FR-05 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 維度 | 約束條件與指標 |
| :---: | :--- | :--- |
| **NFR-01** | 純淨性與依賴 | 100% Python 標準庫，零第三方外部套件依賴。 |
| **NFR-02** | 跨平台路徑一致性 | 所有相對路徑計算結果，統一將 Windows 反斜線 `\` 轉換為標準正斜線 `/`。 |
| **NFR-03** | 執行效能 | 6 步管線全量解算與多 Target 發布總耗時 $\le 1.0$ 秒。 |
