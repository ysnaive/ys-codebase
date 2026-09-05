# 需求討論說明書 (Semantic Requirements Discovery)

> 功能名稱：ecosystem_safe_hot_update_and_jit_synchronization  
> 建立日期：2026-09-03  
> 所屬主計畫：2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance  
> 狀態：Confirmed  
> 計畫類型：Feature  
> 模板版本：v1.2  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：承接 Umbrella 主計畫 `2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance` 之 `sub_01`，落實 [R01 技術調研成果](file:///workspace/ys-codebase/plans/2026_09_02_0533_ecosystem_hot_update_git_decoupling_and_pip_governance/R01_ecosystem_safe_hot_update_and_jit_synchronization.md)，建立生態系全域安全熱更新、JIT 變更感知自愈與 12 小時來源版本探測提示機制。
- **核心目標**：
  1. **`core.contributes` JIT 自愈**：以 $< 2\text{ms}$ 輕量 mtime/size 快照嗅探，在檔案變更時於讀取路徑自動聚合 `contributes.merged.json`，徹底消除手動 `python yscb.py reload` 負擔。
  2. **`agents-workflow` JIT 投影同步**：在工作流 CLI 調用與資產讀取前置特徵指紋比對，來源資產（`assets/`、`contributes`、`snippets/`）變更時自動同步物化至 `.agents/` 等 Targets，徹底消除過期規範與 Agent 幻覺。
  3. **`yscb.py` / `core` 12 小時節流來源版本探測**：非阻塞式探測 Provider `index.json`，在終端溫和提示模組更新，不阻塞正常指令執行，保障 sub-100ms CLI 效能。
  4. **`dev` 模組 Dogfooding 閉環加固**：`dev test` 跑測成功後主動提示直裝引導，並支援 `--sync` 快捷旗標自動完成本地 `@build` 直裝。
- **邊界排除 (Explicitly Excluded)**：
  1. `modules/` 運行端冷啟動再生與 Git 追蹤解耦（明確收斂至後續獨立子計畫 `sub_02`）。
  2. 私有 Pip 微虛擬環境隔離治理與加速外掛（明確收斂至後續獨立子計畫 `sub_03`）。
  3. 引入背景守護進程 (Daemon) 或第三方 `watchdog` 監聽（依據 R01 方案 3 決策排除，採純 Python 標準庫輕量 JIT 嗅探與時間戳節流）。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[P00:DR-01]** 採納 R01 調研推薦之「方案 3：JIT 輕量快照嗅探 + 12 小時節流來源版本探測」架構，零外部依賴、零背景進程，100% 依賴純 Python 標準庫。
- **[P00:DR-02]** `core.contributes` 採用 `cache://core/contributes.meta.json` 記錄各 contributes 檔案之 `mtime` 與 `size`，於 `get()` 讀取路徑執行嗅探，比對耗時控制在 2ms 內，dirty 時原地觸發聚合。
- **[P00:DR-03]** `agents-workflow` 整合 `ReleasePublisher.compute_source_fingerprint()` 至 CLI 前置檢查管線，在來源指紋變更時自動調用 `release_all()` 原子物化至各 Target 目錄。
- **[P00:DR-04]** `UpdateChecker` 採 12 小時（43200 秒）節流與 2 秒短超時，網路探測異常或離線時靜默安全降級，以非阻塞文字提示使用者，絕不阻斷 CLI 主流程。
- **[P00:DR-05]** `dev test` 新增 `--sync` 快捷參數，在測試 100% 通過後直接觸發同名模組之 `install <mod>@build`，達成 Dogfooding 零摩擦四步閉環。

---

## 3. 開放議題與確認紀錄

- [x] 是否遵循子計畫兩層目錄結構約束？（確認，路徑為 `plans/<umbrella>/sub_01_ecosystem_safe_hot_update_and_jit_synchronization/`）
- [x] 是否將 `modules/` Git 解耦收斂移至 `sub_02`？（確認，保持 `sub_01` 聚焦於 JIT 自愈與更新探測）
- [x] 是否已通過 R01 調研完備性驗證？（確認，R01 狀態已 Concluded，方案行之有效）
