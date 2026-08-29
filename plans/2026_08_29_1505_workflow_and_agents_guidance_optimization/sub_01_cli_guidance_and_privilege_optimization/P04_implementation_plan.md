# 實作計畫與定稿審查書 (Implementation Plan & Review)

> 功能名稱：`sub_01_cli_guidance_and_privilege_optimization`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 交叉驗證檢查清單 (Cross-Validation Checklist)

- [x] **需求對齊**：FR-01 ~ FR-08 在 API 規格書與架構設計中均有 1:1 具體介面與檔案承接。
- [x] **邊界防護**：EC-01 ~ EC-05 具備完整的容錯 Fallback 與安全降級機制。
- [x] **依賴純淨**：符合 NFR-01 (100% Stdlib) 與 NFR-02 (微秒級執行效能) 指標約束。
- [x] **測試前置**：P06 測試計畫已涵蓋 FT-01~05、ET-01~02 與 RT-01。

---

## 2. 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :---: | :--- | :---: | :--- |
| **維度 1 (規範)** | `docs/core/contributes.format.md` | Modify | 補充 `commands` 之 `tier` 與 `phases` 宣告規範說明。 |
| **維度 2 (指南)** | `docs/agents-workflow/README.md` | Modify | 說明 ContextInit 職責分離與三級權限防呆手冊機制。 |
| **維度 3 (知識庫)** | `docs/knowledge-db/README.md` | Modify | 補充日常搜尋強制工具替代與 `--ftype` 分流決策樹說明。 |

---

## 3. 架構靈魂拷問 (Stress Test & Resilience Review)

> ❓ **尖銳問題 1 (極端邊界與未知模組容錯)**：  
> 若第三方擴充模組之 `commands` 宣告格式不規範（如缺少 `tier` 欄位、`tier` 為未知字串、或 `phases` 宣告為空/字串），Provider 是否會拋出例外崩潰或中斷 `agents-workflow` 的編譯渲染？  
> 💡 **防護解法**：  
> `get_agents_cli_guild` 與 `get_phase_cli_guild` 內部建立嚴密之型別與欄位防禦（Type Coercion & Safe Fallback），缺失或未知 `tier` 一律自動降級為 `"conditional"` (🟡)，字串形式之 `phases` 自動封裝為列表，任何異常均有預設回退，100% 確保編譯器零崩潰。

> ❓ **尖銳問題 2 (Knowledge-DB 搜尋紀律與原生 grep 衝突)**：  
> 強調禁止以 `grep_search` 進行模糊探索，是否會導致 Agent 在確實需要精確定位單一檔案字串時無所適從？  
> 💡 **防護解法**：  
> 決策樹建立極度明確的例外白名單：若已獲取 100% 精確且唯一的符號/常數全名（如 `foo.doSomethingExact`），允許直接調用原生 `grep_search` 進行單行定位。兩者職責涇渭分明，消滅模糊地帶。

---

## 4. 實作任務清單 (Task Breakdown & Topological Sequence)

- [ ] **TASK-01 (Core Schema & Providers 實作)**：修訂 `source/core/contributes.format.md` 與 `source/core/core/providers.py`，完成三級權限手冊渲染與 `get_phase_cli_guild`。
- [ ] **TASK-02 (Core 單元測試完善)**：修訂 `source/core/tests/test_cli_guild.py`，覆蓋 FT-01、FT-02、ET-01、ET-02。
- [ ] **TASK-03 (全模組 Contributes 宣告更新)**：更新 `core`, `dev`, `knowledge-db`, `agents-workflow` 之 `contributes/core.json`，全面補齊 `tier` 與 `phases`。
- [ ] **TASK-04 (Knowledge-DB 日常搜尋鐵律與 `--ftype` 決策樹強化)**：修訂 `source/knowledge-db/assets/KnowledgeAgentsStandards.md`。
- [ ] **TASK-05 (ContextInit 職責分離與 AgentsStandards 剛性純化)**：修訂 `source/agents-workflow/assets/workflows/ContextInit.md` 與 `source/agents-workflow/assets/standards/AgentsStandards.md`。
- [ ] **TASK-06 (全系統驗證與回歸測試)**：執行 `python yscb.py dev test <module>` 與 `python test/run_regression.py`，確保 100% 通過。

---

## 5. 決策定稿 (Confirmed Decision Records)

- **[P04:DR-01]** 交叉驗證通過，正式定稿實作任務清單與 P06 測試計畫，進入 Phase 5 編碼實作。
