# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：core.commands 活躍執行合約與 CLI 派發管線重構  
> 建立日期：2026-09-07  
> 所屬主計畫：2026_09_07_0831_quality_update (品質更新)  
> 狀態：Confirmed  
> 依據 P01~P03：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md)  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-10 在 API 規格書與架構書中有 100% 對應介面與資料流設計
- [x] **邊界防護**：EC-01 ~ EC-06 均具備具體攔截策略 (拼寫建議、互斥拋錯、缺少參數報錯、熱派發降級、合約缺失、別名衝突)
- [x] **依賴純淨**：符合 NFR-01 ~ NFR-03 約束 (100% Python 標準庫，零第三方依賴，Lazy Loading $\le 5\text{ms}$，未遷移模組測試無斷裂)

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `docs/Core/README.md` | Modify | 登記 `core.commands` 微內核架構、CLI 派發雙管道與精確合約規格 |
| **專題手冊** | `docs/Core/cli_commands_architecture.md` | New | 詳述 Contributes Commands Schema、正交選項群組、CmdBags 物件與相容退化原則 |
| **設計決策** | `docs/Core/DESIGN_NOTES.md` | Modify | 登記 DN-08: 雙管道對稱 Hook 與微內核延遲載入 (PEP 562) 設計考量 |
| **微觀日誌** | `plans/.../changelog.md` | Modify | 記錄子計畫各階段推進成果 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1**：當 Server 在線且命令宣告為 `server_compatible: true`，但 Worker 在執行中因記憶體溢出或崩潰時，使用者終端是否會卡死？  
> 💡 **防護解法**：`dispatcher.py` 在 HTTP IPC 調用時設定 `timeout`（預設 120s 或由環境變數控制），且 MasterSupervisor 內建健康重啟機制；若 HTTP 握手前連線失敗則直接透明降級為本地冷啟動執行 (EC-04)。
>
> ❓ **尖銳問題 2**：`core/__init__.py` 改用 PEP 562 `__getattr__` 後，IDE 的靜態程式碼分析 (如 Pyright / Pylance) 是否會失去型別提示？  
> 💡 **防護解法**：保留 `__all__` 清單以及 `TYPE_CHECKING` 條件導入區塊，確保 IDE 靜態分析與自動補全 100% 正常，同時保證執行期動態按需載入。
>
> ❓ **尖銳問題 3**：`yscb.py` 移除內部黑名單與快取後，如何保證未初始化的工作區執行指令時不會出現難以理解的崩潰堆疊？  
> 💡 **防護解法**：保留工作區與 `yscb.config.json` 探測防線；未初始化時輸出明確友善的指示訊息引導執行 `init` (EC-01 防護)。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01: 核心命令引擎與解析器實作**
  - 新建 `source/core/core/commands/bags.py` (`CmdOption`, `CmdBags`)
  - 新建 `source/core/core/commands/registry.py` (`ArgSpec`, `CommandsRegistry`, 支援 `args` 字典解析與 `choice` 列舉，完全移除 `has_value`)
  - 新建 `source/core/core/commands/resolver.py` (`OptionResolver`, 正交互斥檢查, `args` 必填校驗與 `choice` 合法值校驗)
  - 新建 `source/core/core/commands/help.py` (`HelpRenderer`, 統一模組級與指令級 `--help` 渲染，`<name=[a | b]>` 視覺提示與 `ARGUMENTS` 區塊)
  - 新建 `source/core/core/commands/dispatcher.py` (`CommandDispatcher`, 雙管道派發, 對稱 Hook, 精確調用與退化相容)
  - 新建 `source/core/core/commands/__init__.py` (公開 API 匯出)

- [ ] **TASK-02: 微內核延遲加載與宿主薄化**
  - 重構 `source/core/core/__init__.py`：採用 PEP 562 `__getattr__` 與 `TYPE_CHECKING`，移除 eager imports
  - 重構 `yscb.py`：拔除自製派發、黑名單與模組快取，僅保留 `init`、私有 `.venv` 注入與全量委託 `core.commands.dispatch`

- [ ] **TASK-03: 先驅模組 Contributes 與 CLI 精確合約遷移**
  - 遷移 `source/core/contributes/core.json` 內 `commands` 區塊至新 Schema (包含 `args` 字典與 `choice`，移除 `has_value`)
  - 遷移 `source/server/contributes/core.json` 內 `commands` 區塊至新 Schema (包含 `args` 字典，移除 `has_value`)
  - 改寫 `source/core/scripts/cli.py`：轉為獨立命令函式 (`status(cmd_bags)`, `cmd_uri(cmd_bags)`, 等)，完全移除 `process(args)`
  - 改寫 `source/server/scripts/cli.py`：轉為獨立命令函式 (`start(cmd_bags)`, `stop(cmd_bags)`, 等)，完全移除 `process(args)`
  - 調整 `source/server/server/worker.py`：對接 `core.commands` 派發機制

- [ ] **TASK-04: 自動化單元與整合測試編寫**
  - 編寫 `source/core/tests/test_core_commands.py`，覆蓋 FT-01 ~ FT-10, ET-01 ~ ET-08, PT-01, RT-01

- [ ] **TASK-05: 知識庫與文檔同步交付**
  - 更新 `docs/Core/README.md`、建立 `docs/Core/cli_commands_architecture.md` 與更新 `docs/Core/DESIGN_NOTES.md`

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01] 全域派發與退化相容執行點收斂**：確定所有命令（無論本地或熱派發）的 `process(args)` 舊契約 fallback 唯一收斂在 `core.commands.dispatcher` 的調用網關中，Worker 與本地 cold dispatch 共享同套邏輯，為 `sub_02` 的一鍵清除打下乾淨基礎。
- **[P04:DR-02] IDE 友好之 PEP 562 宣告規範**：在 `core/__init__.py` 中採用 `if TYPE_CHECKING:` 包裹靜態導入，執行期則完全由 `__getattr__` 攔截，兼顧靜態型別推斷與極致冷啟動效能。
- **[P04:DR-03] 參數模型全面統一為 args 字典並徹底移除 has_value**：不向下相容歷史 `has_value` 旗標；子指令位置參數與選項參數全面以 `args` 字典宣告，支援 `description`、`required` 與可選之 `choice` 列舉；Help 自動轉譯為視覺提示（如 `<mode=[a | b]>`），`OptionResolver` 自動完成必填性與列舉合法值校驗。
- **[P04:DR-04] 同構遞迴指令樹與平鋪函式派發**：`CommandSpec` 支援遞迴 `cmd` 樹。`CommandsRegistry` 支援多層走訪；`OptionResolver` 與 `dispatcher` 支援純葉子、純分支與複合分支三態；實作端約定以底線平鋪命名函式（如 `uri_list(bags)`、`uri_resolve(bags)`、`config_get(bags)`）。純分支無函式時自動降級輸出 Help。
