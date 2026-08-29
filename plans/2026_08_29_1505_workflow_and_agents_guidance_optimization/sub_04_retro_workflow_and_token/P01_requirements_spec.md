# 需求規格說明書 (Requirements Specification)

> 功能名稱：開發歷程自檢工作流與擴充 Token (Retro Workflow & Contributed Token)  
> 建立日期：2026-08-29  
> 所屬主計畫：`2026_08_29_1505_workflow_and_agents_guidance_optimization`  
> 狀態：Confirmed  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.5  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `/Retro` 工作流定義與資產建立 | 於 `source/agents-workflow/assets/workflows/Retro.md` 建立自檢工作流，包含頂部「不合規文檔溯源分析 (Documentation-Root-Cause Traceability)」剛性紀律，支援任何 Session 之上下文歷史回顧。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-02** | 核心通用紀律自檢與異常過濾呈遞 | 於 `Retro.md` 內建三大核心原則、執行推進紀律、除錯排查範疇保護與文檔工具紀律之自檢清單；輸出採「異常過濾呈遞」原則，僅列出不符合條目與文檔溯源，全數合規時一行簡短確認。 | P0 | [P00:DR-03], [P00:DR-04] |
| **FR-03** | 擴充 Token 錨點宣告 | 於 `contributes/agents-workflow.json` 之 `token` 註冊 `RETRO_CHECK_ITEMS` 與 `WORKFLOW_RETRO`，並於 `Retro.md` 嵌入 `__@{RETRO_CHECK_ITEMS}__` 與 `__@{WORKFLOW_RETRO}__`。 | P0 | [P00:DR-02] |
| **FR-04** | 貢獻手冊規格與注入範例更新 | 於 `contributes.format.md` 詳列 `RETRO_CHECK_ITEMS` 規範，並提供 `knowledge-db` (Search 效益評測四維度) 與 `core` (CLI Default-Deny 守門) 注入範例。 | P0 | [P00:DR-04] |
| **FR-05** | 開發標準手冊與導出清單同步 | 於 `contributes/agents-workflow.json` 之 `export` 註冊 `Retro.md`，並更新 `DevelopmentStandards.md` 工作流導引清冊。 | P0 | [P00:DR-01] |
| **FR-06** | 編譯、測試與發布回歸驗證 | 新增與更新測試案例，驗證 `Retro.md` 導出、Token 宣告、編譯解析與自引用物化 100% 通過。 | P0 | [P00:DR-05] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 無任何模組注入 `RETRO_CHECK_ITEMS` | `ArtifactCompiler` Stage 1 正確解算並透過 `make_purge_regex` 自動抹除殘留錨點標籤行，產物 0 殘留標籤。 |
| **EC-02** | 對話 Session 極短或無歷史執行紀錄 | 工作流能優雅適應，檢視既有對話上下文，不報錯且輸出對應輕量自檢卡。 |
| **EC-03** | 自檢結果 100% 完美合規 | 輸出簡短聲明「✅ agents-workflow 核心紀律全數合規」，避免無效 Token 膨脹。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 架構解耦 | `agents-workflow` 模組核心保持 100% 通用，零硬編碼外部模組特定檢核邏輯。 |
| **NFR-02** | 測試覆蓋 | 全模組單元測試與契約測試 100% 通過（`python yscb.py dev test agents-workflow`）。 |
| **NFR-03** | 格式相容 | 產出之 CommonMark 與 Frontmatter 100% 相容 Antigravity IDE 工作流解析器。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`** 佔位符二分法：超連結使用 `__#{uri}__`，指令與專案相對路徑使用 `__${uri}__`，確保 CommonMark 連結格式正確。
- **`[!CAUTION]`** Token 錨點命名必須全大寫底線（`RETRO_CHECK_ITEMS`），並在 `contributes/agents-workflow.json` 中正確宣告。
