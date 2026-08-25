# 分類型主計畫總覽 (Umbrella Plan Overview)

> 計畫名稱：agents-workflow 模組全面遷移與升級 (Module agents-workflow Migration & Upgrade)  
> 建立日期：2026-08-25  
> 主計畫目錄：`plans://2026_08_25_2200_agents_workflow_migration/`  
> 當前狀態：進行中 (Phase 0 啟動)  
> 模板版本：v1.4  

---

## 1. 主計畫願景與執行架構 (Master Plan Vision)

本主計畫旨在將專案靈魂模組 **`agents-workflow`** 全面遷移並升級至全新的 YSCB 微內核與單檔 Zip 分發架構中。依開發者指示，本主計畫採**嚴格增量式 (Incremental) 逐步引導**推進。

---

## 2. 子計畫拆分清單與狀態矩陣 (Sub-Plans Matrix)

| 子計畫編號 | 子計畫目錄名稱 | 分流層級 | 當前狀態 | 核心範疇說明 |
| :---: | :--- | :---: | :---: | :--- |
| **sub_01** | `sub_01_core_skeleton_migration` | Full Track | `Completed` | 核心骨架遷移：SOP 本體純淨化、協議產物工廠化與宣告式依賴注入、CLI 自省與 Hook 自治閉環。 |
| **sub_02** | `sub_02_core_contribute_optimization_and_uri_polish` | Full Track | `Completed` | core contribute 依賴注入系統優化（__provider__ 自動標記、拓撲排序、查詢 SDK）與語意 URI 系統打磨（JIT !undefined 熱補齊、6 大空間對稱協議、uri list 自省清冊）。 |
| **sub_03** | `sub_03_workflow_placeholder_format_migration` | Full Track | `Completed` | workflow 佔位符格式修改：遷移為視覺友善的插入佔位符 `__@{token}__` 與路徑佔位符 `__#{uri}__`。 |
| **sub_04** | `sub_04_agents_workflow_injection_config_and_init_default` | Full Track | `Completed` | agents-workflow 專案組態治理 (config.project.json)、4 大 URI 協議貢獻，與一鍵初始化指令 (--init-default)。 |
| **sub_05** | `sub_05_html_annotation_tokens_and_host_uri` | Fast Track | `Completed` | HTML 註解 Token 註冊 (BEGIN/END_HTML_ANNOTATION) 與 core 協議 yscb.host:// 支援。 |

---

## 3. 跨子計畫決策記錄 (Global Decision Records)

- **[UMBRELLA:DR-01] 增量引導原則**：主計畫不進行一次性大跨度設計，由開發者按步驟逐步引導，每一子計畫聚焦於單一最小完整閉環。
- **[UMBRELLA:DR-02] sub_01 聚焦範疇**：`sub_01` 僅聚焦於 SOP 本體與核心骨架，排除 ext 與 ide 指令擴充。
