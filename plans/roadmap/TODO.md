# 專案輕量級待辦與技術債帳本 (TODO Ledger)

> 主題：專案輕量級待辦與技術債帳本  
> 更新日期：2026-10-28  
> 狀態：Active  
> 最後分配編號：3  
> 模型：Gemini 4 Argon (High)  

---

## 待辦清單 (Active TODOs)

### [TODO-01] dev release 第三方間接依賴鎖定 (constraints.txt)
- **建立日期**：2026-10-28
- **目標範疇**：`dev/releaser.py, core/pip_manager.py`
- **備忘與解法要點**：於 dev release 支援匯出或附帶 constraints.txt，並由 pip_manager.py 安裝時帶入 -c 參數，防止第三方間接依賴次版本漂移

### [TODO-02] 業務模組內部 URI 解析邊界收斂 (DIP 依賴反轉)
- **建立日期**：2026-10-28
- **目標範疇**：`knowledge-db, agents-workflow`
- **備忘與解法要點**：漸進式將 core.uri 解析收斂至各模組最外層 scripts/cli.py 與 hook.*.py 入口，使內部引擎接收純 Path 物件以利獨立單元測試

### [TODO-03] core.vfs 本地實體代理定位與遠端快取邊界文檔化
- **建立日期**：2026-10-28
- **目標範疇**：`docs/core`
- **備忘與解法要點**：於 docs/core/README.md 與 uri_protocols.md 明確記載 core.vfs 為具 guard.py 權限守衛之本地實體檔案代理層，並定義未來雲端來源為本地快取物化解析器
