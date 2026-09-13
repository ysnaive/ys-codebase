# 分類型主計畫總覽 (Umbrella Overview)

> 計畫名稱：2026_09_13_1648_downstream_feedback_remediation  
> 建立日期：2026-09-13  
> 狀態：Completed  
> 計畫狀態：Completed  
> Umbrella 模式：Pre-planned (預先規劃型)  
> 模板版本：v1.2  

---

## 1. 主計畫願景與目標 (Vision & Goals)

- **核心願景**：全面修復下游專案回報之 16 項跨模組問題（4 項嚴重、5 項中等、7 項輕微），解決向量維度不相容、發布與更新管線失效、升級目錄換手斷層、設定層級遮蔽、生命週期可觀測性以及管理區塊內容保留等關鍵缺陷，達成升級無障礙與生產就緒。
- **架構邊界**：
  - 涵蓋模組：`knowledge-db`, `core`, `yscb.py` (Host), `server`, `agents-workflow`。
  - 嚴格遵守三大空間協議：源碼修改 100% 於 `source/`，透過標準 `dev test` 跑測驗證，依序推進各子計畫。

---

## 2. 子計畫拆分與執行矩陣 (Sub-Plan Breakdown)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_knowledge_db_embedding_and_diagnostics` | Full Track | `Completed` | 🔴 向量維度動態解析 (移除寫死 384)、🟠 FastEmbed 原生例外診斷、🟡 HF symlink warning 抑制與 index --help 修正 |
| **sub_02** | `sub_02_host_and_core_distribution_lifecycle` | Full Track | `Completed` | 🔴 DEFAULT_PROVIDER_URL 與 self-update 404 修復、🔴 yscb init 自適應最新 core、🔴 modules/ vs .modules/ 換手與相容性檢查、🟡 yscb.py.bak gitignore 與 update_check 刷新 |
| **sub_03** | `sub_03_config_hierarchy_and_hook_observability` | Fast Track | `Completed` | 🟠 config.local 預設值遮蔽 project 修復、🟠 pre_cli_dispatch 等 hook 例外與回傳值可觀測性 (debug/verbose 模式) |
| **sub_04** | `sub_04_server_dependency_and_architecture_migration` | Fast Track | `Completed` | 🟠 server 依賴宣告、熱重載遷移指引、徹底移除舊版 server 影響維持純粹性、Worker Watcher 狀態可觀測性 |
| **sub_05** | `sub_05_agents_workflow_managed_blocks_and_standards` | Fast Track | `Completed` | 🟠 release 覆寫管理區塊時保留自訂擴充列、🟡 舊 managed 檔案清理與 ContextInit.md 引用校準 |
| **sub_06** | `sub_06_agents_workflow_path_placeholder_refactoring` | Fast Track | `Completed` | 🟠 __${uri}__ 語意擴充，支援 __$(起始錨點){uri}__ 動態指定相對路徑起點，維持 project:// 預設映射與 #/$ 語意明確化 |

---

## 3. 主計畫里程碑與推進狀態 (Milestones)

- [x] **里程碑 1**：完成 sub_01 向量嵌入維度動態解析與診斷強化，解除向量檢索降級阻斷
- [x] **里程碑 2**：完成 sub_02 發布提供者、self-update、版本換手與 init 自適應機制修復
- [x] **里程碑 3**：完成 sub_03 組態層級與 hook 例外可觀測性修復
- [x] **里程碑 4**：完成 sub_04 server 依賴宣告、架構遷移說明、徹底移除舊版 server 影響維持純粹與 Watcher 診斷完備
- [x] **里程碑 5**：完成 sub_05 管理區塊保留機制與舊檔案清理
- [x] **里程碑 6**：全模組回歸驗證與結案審查
- [x] **里程碑 7**：完成 sub_06 agents-workflow 路徑佔位符重構 (__$(起始錨點){uri}__ 與語意明確化)
