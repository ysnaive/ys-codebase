# 計畫前置待辦來源清單 (Promoted TODOs)

> 主題：2026_11_03_1701_vscode_support_module_and_core_ide_decoupling  
> 建立日期：2026-11-03  
> 狀態：Active  
> 模型：Gemini 4 Argon (Low)  

---

## 立項待辦條目 (Promoted Items)

### [TODO-18] 修正 _format.json 預設值字面解析不支援浮點數與負數
- **建立日期**：2026-11-03
- **目標範疇**：`core/validator.py`
- **備忘與解法要點**：_parse_default_literal 以 isdigit 判斷整數，導致 'float? = 1.0' 與 'int? = -1' 之預設值被解析為字串；應正確解析 int/float 含負號，並補邊界單元測試
