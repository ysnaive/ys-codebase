<!--
=== AGENT_GUIDANCE: API 規格書 (P03) 填寫規範 ===
1. 定位與目的：
   - 定義具體的 API 介面、型態簽名與屬性方法契約，使用專案實際採用之程式語言撰寫（本模板第 2 節之程式碼區塊僅為語言中立偽代碼示意結構，正式產出時須替換為專案語言的真實語法）。
2. Agent 行為鐵律：
   - 簽名完整性：嚴禁出現省略號或虛構型態，介面必須可直接編譯/執行（依專案實際語言）。
   - 物理/數學單位顯式規範：變數名稱必須標明 _{unit}。
   - 雙軌註解：Public 介面強制附上專案語言慣用之標準文檔註解（XML doc / JSDoc / Docstring / Doxygen 等），Private 工具函式採用敘述式註解。
3. 產出約束：
   - Agent 生成目標文件時，嚴禁輸出本 HTML 註解區塊。
===================================================
-->
# API 規格書 (API Specification)

> 功能名稱：[填入功能名稱]  
> 建立日期：[YYYY-MM-DD]  
> 所屬主計畫：[填入主計畫目錄名稱 / 無]  
> 狀態：Draft / Confirmed  
> 擴充項目：none  
> 模板版本：v1.2  

---

## 1. 類別與成員總覽

| 類別名稱 | 命名空間 / 檔案路徑 | 類型 | 職責概述 |
|---------|-------------------|------|---------|
| `[ClassName]` | `[Namespace]` (`path/to/file.cs`) | Add / Modify | [一句話職責] |

---

## 2. API 介面定義 (Interface Signature & Specs)

### 類別：`[ClassName]`

> 以下以語言中立偽代碼示意結構。正式產出時請替換為專案實際採用語言之真實語法（C# / Python / TypeScript / Rust / Go 等），並附上該語言慣用的標準文檔註解格式（XML doc / JSDoc / Docstring / Doxygen 等）。

```text
# 命名空間/模組路徑依專案語言慣例填寫（例：C# namespace、Python package、Rust mod、Go package 等）

# [類別/介面用途概述]
class [ClassName] extends [BaseClass] implements [IInterface]:

    # ── 屬性 (Properties) ───────────────────────────────────
    # [屬性描述，物理單位顯式後綴如 _px, _ms]
    property width_px: float

    # ── Public 方法 ─────────────────────────────────────────
    # [方法用途]
    # 參數 param1: [參數說明]
    # 回傳: [回傳值說明]
    # 例外/錯誤: [拋出條件，例：ArgumentNullException / ValueError / panic 等，依專案語言慣用錯誤處理機制]
    method MethodName(param1: ParamType) -> ReturnType

    # ── Protected / Internal 虛擬方法 ─────────────────────────
    protected virtual method onStateChanged() -> void
```

---

## 3. 關鍵依賴與第三方套件

| 呼叫功能 | 依賴項目與檔案位置 | 呼叫方式 / 簽名 | 驗證狀態 |
|---------|------------------|---------------|---------|
| [功能描述] | `[Class.Method]` (`path/to/file.cs#L12`) | `[呼叫範例]` | ✅ 已驗證 / ❌ 需新增 |

> **第三方依賴**：若無需引入新第三方套件（NuGet / npm / pip / crates.io / Go Modules 等，依專案語言而定）標記「無」；若有需註明套件名稱、版本與授權。

---

## 4. Decision Records

> 僅在本階段觸發 Deep Discussion 時填寫。ID 格式：`[P03:DR-XX]`。

### [P03:DR-01] [議題標題]
- **議題**：[問題描述]
- **結論**：[最終決定]
- **理由**：[為什麼選擇這個方案]
- **排除方案**：[被排除的方案及原因]
