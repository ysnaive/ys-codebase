# 需求規格說明書 (Requirements Specification)

> 功能名稱：`sub_01_cli_guidance_and_privilege_optimization`  
> 建立日期：2026-08-29  
> 所屬主計畫：`workflow_and_agents_guidance_optimization` (Umbrella Level 2)  
> 狀態：Confirmed  
> 依據 P00：[P00_semantic_requirements.md](./P00_semantic_requirements.md)  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | **Commands Schema 結構擴充** | 擴充 `source/<donor>/contributes/core.json` 中的 `commands.<cmd_name>` 定義，支援 `tier` (`safe` \| `conditional` \| `gated`) 與 `phases` (`list[str]`) 欄位宣告。 | P0 | `[P00:DR-01]`, `[P00:DR-02]` |
| **FR-02** | **AgentsCliGuild.md 動態三級權限編譯** | 升級 `core.providers.get_agents_cli_guild()`，依據 `tier` 屬性將指令分組渲染為 🟢 自主安全、🟡 階段條件、🔴 授權守門三級標籤，並於表頭明確定義權限執行紀律。 | P0 | `[P00:DR-02]` |
| **FR-03** | **Phase-Aware JIT 動態 Provider 實作** | 於 `core.providers` 實作 `get_phase_cli_guild(context, **kwargs)`，依據目標 Phase 自動過濾出該階段允許之推薦指令與防呆紅線清單。 | P0 | `[P00:DR-01]` |
| **FR-04** | **Agents-Workflow JIT 錨點動態注入對接** | `agents-workflow` 透過 `code.func://core/providers:get_phase_cli_guild` 將 JIT 指令引導動態注入至 `PHASE00_AGENTS_GUILD` ~ `PHASE07_AGENTS_GUILD`、`FAST_TRACK_AGENTS_GUILD`、`RESEARCH_AGENTS_GUILD` 等模板註解頂部。 | P0 | `[P00:DR-01]` |
| **FR-05** | **Knowledge-DB 日常檢索鐵律與 `--ftype` 決策樹 (非侵入式)** | 修訂 `source/knowledge-db/assets/KnowledgeAgentsStandards.md`，納入最高優先級之「🚨 執行紀律：日常代碼搜尋強制工具替代」條款，明文禁止以 `grep_search` 進行模糊探索或盲目 `list_dir` / `view_file`，並建立帶 `--ftype=c,cpp,py` (代碼) 與 `--ftype=md` (文檔) 的二分決策樹。 | P0 | `[P00:DR-03]` |
| **FR-06** | **ContextInit.md 與 DevelopmentStandards.md 職責解耦** | 修訂 `source/agents-workflow/assets/workflows/ContextInit.md`，聚焦於 `AgentsStandards`（或 `AGENTS.md`）之剛性必讀建立防呆反射；將 `DevelopmentStandards.md` 的 SOP 細節讀取定調為開啟計畫時按需精讀。 | P0 | `[P00:DR-04]` |
| **FR-07** | **AgentsStandards.md 剛性純化與規範無損鏡像** | 審核並修訂 `source/agents-workflow/assets/standards/AgentsStandards.md`，剝離非防呆禁令之流程描述，並 100% 無損確保所有被剝離內容均收斂於 `DevelopmentStandards.md` 與各 Phase JIT 引導中。 | P0 | `[P00:DR-05]` |
| **FR-08** | **全生態系 Contributes 宣告更新** | 全面更新 `core`, `dev`, `knowledge-db`, `agents-workflow` 之 `contributes/core.json` 宣告，補齊全指令之 `tier` 與 `phases` 標註。 | P0 | `[P00:DR-01]`, `[P00:DR-02]` |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 第三方或既有模組之 `commands` 宣告缺失 `tier` 或 `phases` 欄位 | Provider 提供預設安全 Fallback：`tier` 預設為 `"conditional"`（🟡），`phases` 預設為 `[]`，絕不拋出 KeyError 或造成渲染中斷。 |
| **EC-02** | `tier` 給予未知或非標準字串（如 `"high"`, `"normal"`） | 自動防禦降級為 `"conditional"`（🟡）處理，避免崩潰。 |
| **EC-03** | `phases` 宣告為單一字串而非陣列（例 `"phases": "P05"`） | 自動防禦轉換為列表 `["P05"]`，維持向下相容。 |
| **EC-04** | 當前 Phase 無任何匹配之 CLI 指令（例 Phase 1、Phase 3） | Provider 輸出空字串或通用無特殊限制說明，模板渲染乾淨無殘留佔位符。 |
| **EC-05** | 開發者於 Phase 6 測試時欲執行非本階段允許之指令 | 模板 JIT 註解頂部明確呈現紅線警示，阻斷無效或危險指令調用。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | **依賴純淨性** | 100% Python Standard Library，零第三方套件依賴。 |
| **NFR-02** | **執行效能** | Provider 計算與字串格式化耗時 $< 5\text{ ms}$，不影響 CLI 或工作流編譯器整體響應速度。 |
| **NFR-03** | **測試品質守門** | 新增單元測試覆蓋率 100%，全生態系 4 大模組既有測試回歸 100% Passed。 |
| **NFR-04** | **向下相容性** | 既有 `contributes.core.commands` 查詢介面與資料格式 100% 相容。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]` Dogfooding 資產同步一致性**：
  修訂 `source/agents-workflow/assets/` 與 `source/knowledge-db/assets/` 後，必須透過 `dev release` 或標準流程同步至專案根目錄 `.agents/` 與 `AGENTS.md`，並確保 `<!-- YSCB_AGENTS_BEGIN -->` 軟合併無損。
- **`[!NOTE]` Contributes 聚合機制**：
  Provider 讀取指令時應使用標準 SDK `core.contributes.get("core", "commands")`，以確保所有 Donor 模組與專案層級 `contribute.json` 覆蓋值均已被正確聚合。
