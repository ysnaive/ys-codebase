# 語意需求說明書 (Semantic Requirements Discovery)

> 功能名稱：Agents-Workflow Plan 核查工具鏈升級 (Plan Check & Verification Toolchain Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_04)  
> 狀態：Confirmed  
> 模板版本：v1.1  

---

## 1. 使用者原始需求與意圖 (User Intent)

- **原始陳述**：agents-workflow plan 核查工具鍊升級。對於應產出文件，應檢查於 `.cache/agents-workflow/resolved_contents` 中展開的文件中具備的 `#Header` 是否在產出之文件中皆有對應。並在 CLI 上優化排版（Pass 檔案靜音，僅展示 Fail/Warn 違規項目）。
- **核心目標**：強化 `PlanVerifier` 成為具備動態模板標題鏡像核對、標準 ID 矩陣格式、雙星伴隨 changelog 稽核、Umbrella 巢狀層級防禦、佔位符與 HTML 註解清理、三級嚴重度 (`[PASS]`, `[WARN]`, `[FAIL]`)、Noise-Free CLI 診斷以及歸檔剛性守門之高精度開發計畫合規引擎。
- **邊界排除 (Explicitly Excluded)**：不修改過往已封存之歷史計畫文件。

---

## 2. 核心討論與決策紀錄 (Discussion & Decisions)

- **[sub_04:P00:DR-01] 動態模板章節標題鏡像核對**：`PlanVerifier` 動態讀取 `.cache/agents-workflow/resolved_contents/templates/<template>.md`，解析模板展開後定義之 Markdown 章節標題（`#`, `##`, `###` Header），檢查產出文件是否 100% 具備並鏡像對應模板章節標題，缺漏標記 `[FAIL]`。
- **[sub_04:P00:DR-02] 測試規劃與標準 ID 格式合規**：檢核所有產出文件內之 ID 前綴格式（`FR-XX`, `EC-XX`, `NFR-XX`, `[{Phase}:DR-XX]`, `FT-XX`, `ET-XX`, `RT-XX`, `UX-XX`），檢核 P06 測試案例具備合法 FT/ET 前綴，不進行跨檔案超剛性字串 1:1 鎖定。
- **[sub_04:P00:DR-03] Header 元數據完整性**：檢查 Blockquote 中必填欄位 `功能名稱`, `建立日期`, `狀態`；子計畫必須具備 `所屬主計畫`。
- **[sub_04:P00:DR-04] 雙星伴隨與 changelog 合規**：伴隨 `changelog.md` 存在性、標準表格結構與最新記錄。
- **[sub_04:P00:DR-05] 巢狀層級約束與 Umbrella 稽核**：限制層級 $\le 2$ 層；Umbrella 主計畫必須具備 `umbrella_overview.md` 與子目錄一致。
- **[sub_04:P00:DR-06] 佔位符與嚴禁殘留任何 HTML 註解**：檢測未清除之 HTML 註解與未替換佔位符，違者標記 `[FAIL]`。
- **[sub_04:P00:DR-07] 嚴重度分級、CLI 噪聲抑制 (Noise-Free) 與歸檔守門阻斷**：`[PASS]`/`[WARN]`/`[FAIL]`；全 Pass 輸出單行，有錯時隱藏 Pass 檔案僅聚焦輸出違規項；`plan archive` 遭遇 Fail 剛性阻斷（需 `--force`）。

---

## 3. 開放議題與確認紀錄

- [x] **追溯鏈寬度確認**：放寬跨檔案超剛性比對，專注 FT/ET 格式合規。
- [x] **CLI 排版手感確認**：Pass 文件自動隱藏，聚焦輸出問題項目。
- [x] **HTML 註解約束確認**：嚴禁產出與歸檔文件殘留任何 HTML 註解。
