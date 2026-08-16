# API 規格書 (API Specification)

> 功能名稱：[填入功能名稱]
> 建立日期：[YYYY-MM-DD]
> 狀態：Draft / Confirmed
> 模板版本：v1.0

---

## 類別總覽

| 類別名稱 | 類型 | 命名空間 | 對應變更清單 |
|---------|------|---------|-------------|
| [ClassName] | Add / Modify | [Namespace] | Add-1 / Modify-1 |

---

## 詳細 API 設計

### 類別：[ClassName]

> **變更類型**：Add / Modify
> **檔案路徑**：[[path/to/file]]
> **職責**：[一句話描述]

#### Public API

##### [MethodName]

```text
public ReturnType MethodName(ParamType1 param1, ParamType2? param2 = null)
```

| 項目 | 說明 |
|------|------|
| **用途** | [簡要描述] |
| **參數** | `param1` (ParamType1)：[描述] |
|          | `param2` (ParamType2?, 預設 null)：[描述] |
| **回傳** | [描述回傳值及其意義] |
| **錯誤處理** | [什麼情況拋什麼例外 / 回傳 null / 其他策略] |
| **備註** | [其他需要注意的事項] |

**呼叫端範例**：
```text
// 預期使用方式
var obj = new ClassName();
var result = obj.MethodName(value1, value2);
if (result == null)
{
    // 錯誤處理
}
```

---

#### Protected / Internal API

##### [MethodName]

```text
protected virtual void MethodName(ParamType param)
```

| 項目 | 說明 |
|------|------|
| **用途** | [簡要描述] |
| **精確度** | 100%（Protected）/ 80%（Internal/Private，實作中可微調） |

---

#### Private API（精確度 80%）

> 以下 Private API 允許在實作中微調，但微調必須記錄在 `P05_task.md` 中。

| 方法簽名 | 用途 |
|---------|------|
| `private void HelperMethod(...)` | [簡要描述] |

---

## 依賴引用清單

| 功能 | 依賴項 | 位置 | 呼叫方式 | 驗證狀態 |
|------|--------|------|---------|---------|
| [功能描述] | [類別.方法名] | [[path/to/file]:L行號] | [實際呼叫程式碼] | ✅ 已驗證 / ❌ 不可達 |

---

## 第三方依賴

> 如果無需引入新的外部依賴，標記「無」即可。

| 套件名稱 | 版本 | 授權協議 | 維護狀態 | 用途 | 替代方案 |
|---------|------|---------|---------|------|---------|
| [Package] | [x.y.z] | [MIT/Apache/...] | [活躍/維護中/棄用] | [為什麼需要] | [有無替代] |

---

## Decision Records

> 僅在本階段觸發 Deep Discussion 時填寫。

### DR-01: [議題標題]
- **議題**：[問題描述]
- **結論**：[最終決定]
- **理由**：[為什麼選擇這個方案]
- **排除方案**：[被排除的方案及原因]
