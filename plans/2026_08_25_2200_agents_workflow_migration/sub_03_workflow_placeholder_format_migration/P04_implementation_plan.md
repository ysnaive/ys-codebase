# Phase 4: 實作計畫與定稿審查 (Implementation Plan) - workflow 佔位符格式修改

> 計畫名稱：`sub_03_workflow_placeholder_format_migration`  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 依據設計規格：[P01_requirements_spec.md](./P01_requirements_spec.md), [P02_architecture_plan.md](./P02_architecture_plan.md), [P03_api_spec.md](./P03_api_spec.md)  
> 當前狀態：`Confirmed` (Phase 4 審查定稿完成)  
> 擴充項目：none  
> 模板版本：v1.4  

---

## 1. 跨階段對齊審查表 (Cross-Phase Alignment Matrix)

| P00 語意決策 | P01 需求規格 | P02 架構設計 | P03 API 介面 | P06 測試案例 | 1:1 對齊狀態 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| `[P00:DR-01]` 佔位符正則空白容錯 | FR-01, FR-03 | §2.1 TOKEN_ANCHOR_REGEX | §1.1, §2.1 make_token_tag_regex | FT-01, FT-02 | 100% 對齊 |
| `[P00:DR-02]` 路徑佔位符語意保留 | FR-02 | §2.1 URI_REF_REGEX | §1.2 URI Reference Schema | FT-03 | 100% 對齊 |
| `[P00:DR-03]` 5-Step 狀態機三模式注入 | FR-04, FR-05, EC-01, EC-02, EC-04 | §2.2 狀態機時序圖, ADR-02 | §2.2 resolve_single_artifact | FT-01, FT-04, FT-05, ET-01, ET-02, ET-04 | 100% 對齊 |
| `[P00:DR-04]` 全量資產遷移與舊語法清除 | FR-06, FR-07, FR-08 | §4 模組衝擊清單 | §1 Schema 規範 | FT-06, ET-03, RT-01, UX-01 | 100% 對齊 |

---

## 2. 專案文檔衝擊預排清單 (Documentation Impact Plan)

依據知識庫 7 大抽象維度管理規範，預排本次子計畫結案時需 1:1 交付之文檔衝擊：

| 維度編號 | 維度名稱 | 目標文檔路徑 | 預排交付內容摘要 |
| :---: | :--- | :--- | :--- |
| **維度 2** | 核心概念與機制手冊 | `docs/agents-workflow/README.md` | 更新佔位符語法章節，說明 `__@{token}__` 與 `__#{uri}__` 之語意與視覺化優勢。 |
| **維度 5** | 工程妥協與設計筆記 | `docs/agents-workflow/DESIGN_NOTES.md` | 登記 `[DN-AW-04]`（佔位符 Markdown 可視化格式選型與殘留抹除策略）。 |
| **維度 7** | 全專案發布變更日誌 | `CHANGELOG.md` | 追加 `sub_03` 佔位符格式重構發布摘要。 |

---

## 3. 實作前兩大靈魂拷問 (Stress Test Questions)

### 拷問 1：舊版 HTML 註解格式若在未知擴充或歷史模板中出現，編譯器是否會崩潰？
- **答覆**：**絕對不會**。新版正則 `TOKEN_ANCHOR_REGEX` 僅匹配 `__@{...}__`，任何舊格式（如 `<!-- __TOKEN__ -->`）在編譯器眼中等同於一般純文字段落，會被原樣輸出保留，不會產生任何異常崩潰或非預期替換。

### 拷問 2：若路徑佔位符 `__#{uri}__` 包含複雜語意協議或包含空格，正則是否能穩健匹配並安全保留？
- **答覆**：**完全穩健**。路徑正則採用 `r"__#\{\s*([^}]+)\s*\}__"`，以 `[^}]+` 貪婪捕捉大括號內所有有效字元（包含 `:`, `/`, `_`, `-`, `.` 等），並於狀態機 Step 5 完全忽略不作內容替換，確保 Markdown 語意參照 100% 不變。

---

## 4. 實作任務拆解清單 (Task Breakdown)

- [ ] **TASK-01 (編譯器正則引擎與 5-Step 狀態機升級)**：修改 `source/agents-workflow/agents_workflow/compiler.py`，全面實作 `__@{token}__` 匹配、三模式注入與殘留抹除，確保 `__#{uri}__` 原樣保留。
- [ ] **TASK-02 (全系統標準模板庫 1:1 語法遷移)**：更新 `source/agents-workflow/assets/templates/` 下所有 P01~P07 標準模板，將標頭錨點替換為 `__@{PHASEXX_STANDARD_HEADER}__`。
- [ ] **TASK-03 (規範手冊與工作流導引文檔 1:1 遷移)**：更新 `assets/standards/DevelopmentStandards.md`（`__@{PROJECT_SPECIFIC_STANDARDS}__`）與 `assets/workflows/ContextInit.md`（`__@{DYNAMIC_CONTEXT_MAP}__`）。
- [ ] **TASK-04 (單元測試更新與全模組回歸驗證)**：更新 `tests/test_compiler.py` 覆蓋 FT-01~06、ET-01~04，並實機執行 `python yscb.py dev test --all`（維持 97+ 測試 100% Passed）。

---

## 5. 當前階段確認狀態

- **當前狀態**：`Confirmed` (Phase 4 審查定稿完成)  
- **推進關卡**：等待開發者指示「**開始實作**」，以推進至 Phase 5 初始化任務清單並編寫程式碼！
