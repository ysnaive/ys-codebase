# 專案輕量級待辦與技術債帳本 (TODO Ledger)

> 主題：專案輕量級待辦與技術債帳本  
> 更新日期：2026-11-06  
> 狀態：Active  
> 最後分配編號：25  
> 模型：Unknown  

---

## 待辦清單 (Active TODOs)

### [TODO-01] dev release 第三方間接依賴鎖定 (constraints.txt)
- **建立日期**：2026-10-28
- **目標範疇**：`dev/releaser.py, core/pip_manager.py`
- **備忘與解法要點**：於 dev release 支援匯出或附帶 constraints.txt，並由 pip_manager.py 安裝時帶入 -c 參數，防止第三方間接依賴次版本漂移

### [TODO-02] 業務模組內部 URI 解析邊界收斂 (DIP 依賴反轉)
- **建立日期**：2026-10-28
- **目標範疇**：`file-space, ast, knowledge-db, agents-workflow`
- **備忘與解法要點**：漸進式將 core.uri 解析收斂至各模組最外層 scripts/cli.py 與 hook.*.py 入口，使內部引擎接收純 Path 物件以利獨立單元測試

### [TODO-19] 擴充 vscode-support 支援 snippets, grammars, problem_matchers 與 configuration_defaults 擴充點合成
- **建立日期**：2026-11-03
- **目標範疇**：`vscode-support`
- **備忘與解法要點**：於 contributes/_format.json 與合成器擴充支援 VS Code 本地外掛之語法高亮、代碼片段、ProblemMatcher 與預設組態注入

### [TODO-20] 調研跨宿主與受限容器環境 (如 virtiofs 禁建 symlink) 下 current-site-packages 無版本號穩定路徑之零連結替代方案
- **建立日期**：2026-11-03
- **目標範疇**：`module:vscode-support, module:core`
- **備忘與解法要點**：目前採方案 C 恆定寫入 ./ys_codebase/.venv/current-site-packages 並保留宿主機已建連結；後續調研是否支援無 symlink/junction 之純目錄或路由機制

### [TODO-21] 完整調研、整理 event broadcast 架構與現有 event，並加入 CLI pre-flight 檢查供各模組 hook 進行健康度排查
- **建立日期**：2026-11-04
- **目標範疇**：`core, ecosystem modules`
- **備忘與解法要點**：盤點並正規化 core.events 廣播生命週期與既有事件契約，新增 CLI pre-flight 事件掛鉤供各模組執行前置健康度自檢

### [TODO-23] 將 SyncCoordinator._precreate_remote_dirs() 升級為依深度分層 (Level-by-Level BFS) + 同層 ThreadPoolExecutor 平行 mkdir 並為 _folder_cache 加上執行緒鎖
- **建立日期**：2026-11-04
- **目標範疇**：`ys_codebase/source/gdrive-support/gdrive_support/{coordinator.py,transport.py}`
- **備忘與解法要點**：當同步大量子目錄 (如 plans/archived 272 個資料夾) 時，同深度層級的父目錄已由上一層建立完畢，可按 depth 分組後以 ThreadPoolExecutor(max_workers=8) 平行執行 mkdir，並於 GoogleDriveApiTransport 為 _folder_cache / _scanned_prefixes 加入執行緒鎖保護
