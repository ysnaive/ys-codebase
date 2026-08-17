# API 規格書 (API Specification)

> 功能名稱：[填入功能名稱]
> 建立日期：[YYYY-MM-DD]
> 狀態：Draft / Confirmed
> 模板版本：v1.1

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
