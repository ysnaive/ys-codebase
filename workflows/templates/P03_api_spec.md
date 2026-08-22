<!--
=== AGENT_GUIDANCE: API 規格書 (P03) 填寫規範 ===
1. 定位與目的：
   - 定義具體的 API 介面、型態簽名、屬性方法契約與 Doxygen / XML 註解。
2. Agent 行為鐵律：
   - 簽名完整性：嚴禁出現省略號或虛構型態，介面必須可直接編譯。
   - 物理/數學單位顯式規範：變數名稱必須標明 _{unit}。
   - 雙軌註解：Public 介面強制 Doxygen/XML 註解，Private 工具函式採用敘述式註解。
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

## 2. API 介面定義 (C# Signature & Specs)

### 類別：`[ClassName]`

```csharp
namespace UIToolkit.[Subsystem];

/// <summary>
/// [類別用途概述]
/// </summary>
public class [ClassName] : [BaseClass], [IInterface]
{
    // ── 屬性 (Properties) ───────────────────────────────────
    /// <summary>[屬性描述，物理單位顯式後綴如 _px, _ms]</summary>
    public float width_px { get; set; }

    // ── Public 方法 ─────────────────────────────────────────
    /// <summary>
    /// [方法用途]
    /// </summary>
    /// <param name="param1">[參數說明]</param>
    /// <returns>[回傳值說明]</returns>
    /// <exception cref="ArgumentNullException">[例外拋出條件]</exception>
    public ReturnType MethodName(ParamType param1);

    // ── Protected / Internal 虛擬方法 ───────────────────────
    protected virtual void onStateChanged();
}
```

---

## 3. 關鍵依賴與第三方套件

| 呼叫功能 | 依賴項目與檔案位置 | 呼叫方式 / 簽名 | 驗證狀態 |
|---------|------------------|---------------|---------|
| [功能描述] | `[Class.Method]` (`path/to/file.cs#L12`) | `[呼叫範例]` | ✅ 已驗證 / ❌ 需新增 |

> **第三方依賴**：若無需引入新 NuGet 套件標記「無」；若有需註明套件名稱、版本與授權。

---

## 4. Decision Records

> 僅在本階段觸發 Deep Discussion 時填寫。

### DR-01: [議題標題]
- **議題**：[問題描述]
- **結論**：[最終決定]
- **理由**：[為什麼選擇這個方案]
- **排除方案**：[被排除的方案及原因]
