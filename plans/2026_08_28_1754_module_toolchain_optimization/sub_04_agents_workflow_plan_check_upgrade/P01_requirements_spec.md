# 需求規格說明書 (Requirements Specification)

> 功能名稱：Agents-Workflow Plan 核查工具鏈升級 (Plan Check & Verification Toolchain Upgrade)  
> 建立日期：2026-08-28  
> 所屬主計畫：`plans://2026_08_28_1754_module_toolchain_optimization/` (sub_04)  
> 狀態：Confirmed  
> 模板版本：v1.4  

---

## 1. 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格描述 | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | 動態模板章節標題鏡像核對 | 動態讀取 `.cache/agents-workflow/resolved_contents/templates/<template>.md` 提取 Markdown 標題清單，檢查產出文件是否 100% 具備並鏡像對應（遺漏標記 `[FAIL]`）。 | P0 | [sub_04:P00:DR-01] |
| **FR-02** | 測試規劃與標準 ID 格式合規 | 檢查所有產出文件內之 ID 前綴是否符合規範格式（`FR-XX`, `EC-XX`, `NFR-XX`, `[{Phase}:DR-XX]`, `FT-XX`, `ET-XX`, `RT-XX`, `UX-XX`）；檢查 `P06_test_plan.md` 測試案例具備合法 FT/ET 前綴。 | P0 | [sub_04:P00:DR-02] |
| **FR-03** | Header 元數據完整性檢核 | 檢查 Markdown 開頭 Blockquote 之 `功能名稱`, `建立日期`, `狀態`；二級子計畫必須具備 `所屬主計畫`。 | P0 | [sub_04:P00:DR-03] |
| **FR-04** | 雙星伴隨與 changelog 合規 | 檢查計畫目錄下必須伴隨 `changelog.md`，且具備標準表格與合法記錄類型（`INIT`, `DECISION`, `PHASE`, `REVIEW`, `DEVIATION` 等）。 | P0 | [sub_04:P00:DR-04] |
| **FR-05** | 巢狀層級與 Umbrella 主計畫稽核 | 嚴格限制目錄層級 $\le 2$ 層；Umbrella 主計畫必須具備 `umbrella_overview.md` 且子計畫清冊同步。 | P0 | [sub_04:P00:DR-05] |
| **FR-06** | 佔位符與嚴禁殘留 HTML 註解 | 檢查是否殘留 HTML 註解，或未替換之佔位符（違者標記 `[FAIL]`）。 | P0 | [sub_04:P00:DR-06] |
| **FR-07** | 三級嚴重度、CLI 噪聲抑制與歸檔阻斷 | 輸出分級 `[PASS]`, `[WARN]`, `[FAIL]`；全 Pass 輸出單行，有錯時隱藏 Pass 檔案僅聚焦輸出違規項；`plan archive` 遭遇 Fail 剛性阻斷（需 `--force`）。 | P0 | [sub_04:P00:DR-07] |

---

## 2. 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 動態模板快取目錄不存在 | 若 `.cache/agents-workflow/resolved_contents/templates/` 尚未編譯，自動調用 `ArtifactCompiler` 執行即時解析或降級至預設模板檢查，不拋出未捕獲例外。 |
| **EC-02** | 空計畫目錄或非 Markdown 檔案 | 跳過非 `.md` 檔案，若計畫目錄為空或無任何合法文件，標記為 `[FAIL]`。 |
| **EC-03** | 歷史已歸檔計畫容錯 | 歷史歸檔計畫 (`archive_plans/`) 可能採用早期模板格式，核查時允許寬鬆模式或以 `[WARN]` 提醒。 |

---

## 3. 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 效能指標 | 單一計畫完整 Markdown 與章節解析耗時 $\le 50\text{ms}$，全量計畫檢核 $\le 300\text{ms}$。 |
| **NFR-02** | 終端診斷排版 (Noise-Free) | 終端排版清晰、顏色分明；無錯誤時單行收斂，有錯誤時精確標註 `(檔案名稱:行號) [類別] 違規說明`。 |
| **NFR-03** | 機器可讀支援 | `plan check` 支援 `--json` 旗標輸出結構化 JSON，方便 CI 與自動化審查工具整合。 |

---

## 4. 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!NOTE]`**：解析 Markdown 模板 `# Header` 時需正規化去除前綴 `#`、數字編號與中英空白，保障彈性匹配。
- **`[!CAUTION]`**：掃描佔位符與 HTML 註解時需過濾代碼塊 (``` ... ```) 與行內代碼 (`...`)，杜絕文檔說明引起之誤報。
