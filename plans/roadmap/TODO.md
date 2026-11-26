# 專案輕量級待辦與技術債帳本 (TODO Ledger)

> 主題：專案輕量級待辦與技術債帳本  
> 更新日期：2026-11-25  
> 狀態：Active  
> 最後分配編號：34  
> 模型：Gemini 4 Neon (XHigh)  

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

### [TODO-26] 修復 Windows 嵌套 ISOLATED_SANDBOX 路徑突破 260 字元 MAX_PATH
- **建立日期**：2026-11-14
- **目標範疇**：`ys_codebase/source/dev/dev/testing/sandbox.py`
- **備忘與解法要點**：當外層已在沙盒內時將 ISOLATED_SANDBOX 分配於外層同級沙盒目錄，消除 shutil.copytree WinError 3

### [TODO-27] 正規化 TestVFS Windows os.readlink 長路徑前綴斷言
- **建立日期**：2026-11-14
- **目標範疇**：`ys_codebase/source/core/tests/test_vfs.py`
- **備忘與解法要點**：test_vfs_open_boundary_guard_lf_newline_and_symlink_copy 剝除 Windows readlink 回傳之長路徑前綴後再比對 outside_dir

### [TODO-28] 統一鎖定 Deterministic Zip 之 ZipInfo.create_system=3 消除跨平台發布雜湊差異
- **建立日期**：2026-11-14
- **目標範疇**：`ys_codebase/source/dev/dev/builder.py, ys_codebase/source/core/core/engine.py, yscb.py, .github/workflows/`
- **備忘與解法要點**：於 5 處 ZipInfo 建構點顯式設定 create_system = 3，避免 Windows 預設 0 與 Linux 預設 3 造成 dev release 之 index.json sha256 被 ci-sha256-gate 攔截

### [TODO-29] 評估 atomic.py Windows ACL/SID 模擬 0o600 權限之必要性
- **建立日期**：2026-11-21
- **目標範疇**：`core_v2/source/core/core/filesystem/fs/atomic.py`
- **備忘與解法要點**：核對本機開發工具場景下 _WinSidAndAttributes 與 Win32 SD/ACL 防護是否值得保留或簡化

### [TODO-30] 補齊 core_v2 測試框架 Windows 孤兒行程查殺
- **建立日期**：2026-11-25
- **目標範疇**：`core_v2/tests/_harness.py`
- **備忘與解法要點**：_collect_live_tmp_root_orphans 在 os.name=='nt' 目前回傳空清單，改以 Win32 API 或 powershell/CIM 掃描帶 tmp_root 標記的殘留測試行程，防止 Windows 異常中斷時孤兒 Daemon 鎖檔

### [TODO-32] Core 2.0 內建 yscb diag 診斷與報表 CLI UX (perf/logs/inspect/bundle)
- **建立日期**：2026-11-25
- **目標範疇**：`core_v2/source/core/core/surface/bootstrap/system_module.py`
- **備忘與解法要點**：在 3+1 JSONL 日誌與 ImTK 風格 Profiler 引擎落地後，視需要補齊 yscb diag perf/logs/inspect/bundle（含跨流 trace_id 串查、Chrome Trace 匯出、即時鎖與 Worker 現場檢視、一鍵脫敏問題回報包）

### [TODO-33] Core 2.0 Daemon 活體執行現場檢視 (in-flight tasks/locks/waiters/bg_errors)
- **建立日期**：2026-11-25
- **目標範疇**：`core_v2/execution/daemon, core_v2/execution/runtime`
- **備忘與解法要點**：擴充 DaemonStatusSnapshot 與控制查詢，讓線上卡住或慢跑時可即時看到進行中 trace_id/task_id/耗時、resource_key 持有者與 SERIALIZE/COALESCE/QUIESCE 佇列等候明細及近期背景錯誤內容

### [TODO-34] Core 2.0 CLI 熱轉發路徑瘦身與 Bootstrap/Launcher 耗時剖析優化
- **建立日期**：2026-11-25
- **目標範疇**：`core_v2/yscb.py, core_v2/surface/cli, core_v2/surface/bootstrap`
- **備忘與解法要點**：拆解並縮減 Bootstrap/Launcher (~500ms) 啟動黑箱，並讓純轉發線上 Daemon RPC 之 CLI 請求繞過冷 CreateKernel 與 SpaceDb 初始化 (省去 ~165ms 熱啟動稅)
