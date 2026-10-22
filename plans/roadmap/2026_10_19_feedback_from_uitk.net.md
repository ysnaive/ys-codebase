# knowledge-db `callers` 問題回報（C# 專案）

**環境**：`python yscb.py knowledge-db`（uitk.net 專案，.NET 8 / C#）；倒排索引、向量索引皆已建立（`BAAI/bge-small-zh-v1.5`），`src` 空間 244 檔、`tests` 空間 139 檔。

## 問題 1：`--json` 模式崩潰
- **指令**：`python yscb.py knowledge-db callers MarkMeasureDirty --json`（`CalculateLayout`、`UpdateLayout`、`UpdateMetrics` 也一樣）
- **實際**：輸出 `[knowledge-db] 執行異常: 'caller_symbol'`，exit code 1，stdout 沒有 JSON。
- **非 JSON 模式**：同一指令可以正常輸出清單。
- **推測**（未證實）：caller 清單混入 Markdown 文件命中（見問題 3），這類條目可能沒有 `caller_symbol` 欄位，JSON 序列化時觸發 `KeyError`。

## 問題 2：C# 呼叫點大量漏報

以全庫文字搜尋（`*.cs`）作為基準對照：

| 目標符號 | 實際呼叫來源 (src 檔數 / tests 檔數) | callers 回報之程式碼來源 | 漏報範例 |
| :--- | :---: | :---: | :--- |
| `VisualElement.MarkMeasureDirty` | 8 / 4 | 1（`InlineStyle.cs`） | `VisualElementHierarchy.cs` L47 `m_Owner.MarkMeasureDirty();`、`TextElement.cs` L49 `MarkMeasureDirty();`、`TextField.cs`（10 處）、`ScrollView.cs` L489、`Panel.cs` L204 |
| `VisualElement.MarkArrangeDirty` | 6 / 1 | 1（`InlineStyle.cs`） | `VisualElementHierarchy.cs` L48、`TextField.cs`、`Panel.cs` L205 |
| `FlexLayoutEngine.CalculateLayout` | 4 / 9 | 1（`VisualElement.Layout.cs` L232） | `ScrollView.cs` L497 `FlexLayoutEngine.CalculateLayout(this, ...)`、`Panel.cs` L583 `UIToolkit.UI.Layout.FlexLayoutEngine.CalculateLayout(...)`（完整命名空間限定）、`FlexLayoutEngine.cs` L544/602/684（遞迴自呼叫）、9 個測試檔 |
| `ScrollView.ScrollTo` | 1 / 2 | 0 | `RecorderMainWindow.cs` L1132/1192 `m_TimelineScrollView.ScrollTo(row)`、`sandbox/.../Program.cs` L308 |
| `ScrollView.UpdateMetrics` | 1 / 1 | 0 | `ScrollView.cs` L313/480/511（同類別內隱含 `this` 呼叫）、`ScrollViewTests.cs`（13 處） |
| `IPanel.UpdateLayout` | 1 / 4 | 1（測試檔） | `PanelManagerModule.cs` L161 `panel.UpdateLayout();`、`RecorderAppController.cs`（10 處） |

**觀察到的漏報型態**（僅是推測，未驗證）：
1. 隱含 `this` 的呼叫：`MarkMeasureDirty();`、`UpdateMetrics();`
2. 透過欄位或區域變數接收者的呼叫：`m_Owner.X()`、`panel.X()`、`m_TimelineScrollView.X()`
   - 但 `InlineStyle` 的 `m_Owner.MarkMeasureDirty()` 有被抓到，差別可能在它是寫在 expression-bodied property setter 裡。
3. 完整命名空間限定的呼叫：`UIToolkit.UI.Layout.FlexLayoutEngine.CalculateLayout(...)`
4. 遞迴自呼叫
5. 位於 `override` 方法內的呼叫（`ScrollView.onBeginRender`）
6. 目標為介面方法（`IPanel.UpdateLayout`）時，沒有關聯到實作類別 `Panel.UpdateLayout` 的呼叫端

## 問題 3：caller 清單混入 Markdown 文字提及
- **現象**：`callers CalculateLayout` 回報的 5 筆裡有 4 筆是 `.md`（`handoff.md`、`R01_*.md` 的標題段落），只有 1 筆是程式碼。
- **建議**：callers / impact 預設只回報程式碼，或提供 `--ftype` 過濾。

## 問題 4：`impact` 同樣受影響
- `impact MarkMeasureDirty --depth=1` 只回報 `InlineStyle`，原因和問題 2 相同。
- 這會讓重構影響面評估明顯低估。

## 影響
專案規範要求呼叫鏈排查只能用 `callers` / `impact`，並禁止目錄級 grep。但在 C# 專案裡這兩個工具的結果不完整，會讓改動範圍評估出現系統性低估。本次只能經人工授權後改用全庫文字搜尋補齊。

## 最小重現
```bash
python yscb.py knowledge-db callers MarkMeasureDirty --json   # 崩潰 'caller_symbol'
python yscb.py knowledge-db callers MarkMeasureDirty          # 僅 1 個來源
grep -rnE --include=*.cs 'MarkMeasureDirty\(' src tests | grep -v /obj/ | wc -l   # 實際 68 處 / 12 檔
```
