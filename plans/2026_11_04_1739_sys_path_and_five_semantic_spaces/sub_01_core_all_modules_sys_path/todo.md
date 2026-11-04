# 計畫前置待辦來源清單 (Promoted TODOs)

> 主題：sub_01_core_all_modules_sys_path  
> 建立日期：2026-11-04  
> 狀態：Completed  
> 模型：Unknown  

---

## 立項待辦條目 (Promoted Items)

### [TODO-22] 補齊 vscode-support 對 YSCB 模組與源碼搜尋路徑之 python.analysis.extraPaths 投影
- **建立日期**：2026-11-04
- **目標範疇**：`ys_codebase/source/vscode-support/vscode_support/projector.py`
- **備忘與解法要點**：目前 extraPaths 僅注入 current-site-packages，未包含已安裝模組 (.modules/<mod>) 或母倉源碼 (source/<mod>)，且 .modules 被列入 python.analysis.exclude，導致 Pylance 無法解析 from core import uri, vfs 等跨模組匯入；需讓 SettingsProjector 自動投影已安裝模組/源碼路徑並支援 clean revert
