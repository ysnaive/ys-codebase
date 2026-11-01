# 計畫前置待辦來源清單 (Promoted TODOs)

> 主題：sub_02_core_infra_resilience  
> 建立日期：2026-11-01  
> 狀態：Active  
> 模型：Gemini 4 Argon (Low)  

---

## 立項待辦條目 (Promoted Items)

### [TODO-03] core.vfs 本地實體代理定位與遠端快取邊界文檔化
- **建立日期**：2026-10-28
- **目標範疇**：`docs/core`
- **備忘與解法要點**：於 docs/core/README.md 與 uri_protocols.md 明確記載 core.vfs 為具 guard.py 權限守衛之本地實體檔案代理層，並定義未來雲端來源為本地快取物化解析器

### [TODO-07] pip_manager ensure_venv 與 _bootstrap_pip 改拋 PipInstallError 避免無 ensurepip 環境冷啟動連坐崩潰
- **建立日期**：2026-11-01
- **目標範疇**：`core (pip_manager.py, installer.py)`
- **備忘與解法要點**：將 ensure_venv 與 _bootstrap_pip 拋出之 RuntimeError 統一改為 PipInstallError，使 installer.sync_pip_dependencies 能攔截並降級為 Warning，不阻斷零依賴模組冷啟動自舉

### [TODO-11] 報錯尾端 [Agent Directive] 技能路由注入、Windows 安裝前主動通知 Server 釋放句柄與 .old_* 延遲清理及 VFS 註解收斂
- **建立日期**：2026-11-01
- **目標範疇**：`core, dev, server (validator.py, installer.py, engine.py, vfs.py, checker.py)`
- **備忘與解法要點**：1. 於 validator.py 與 checker.py 報錯尾端注入 [Agent Directive] 指引查閱對應 Skill；2. 於 installer.py 生命周期變異前主動通知活躍 Server 停機/卸載 Worker 釋放 .pyd/.dll 句柄，並對 .old_* 採非阻塞容錯延遲回收；3. 清理 vfs.py 不切實際之 MemoryBackend 註解

### [TODO-12] cmd_restore 版本號比對修復 (根治跨分支 auto-restore 死迴圈) 與 plan verify 硬編碼絕對路徑可攜性警告
- **建立日期**：2026-11-01
- **目標範疇**：`yscb.py, core (installer.py), agents-workflow (verifier.py)`
- **備忘與解法要點**：1. 修正 yscb.py 與 installer.py 之 cmd_restore 跳過條件，比對已安裝 manifest.json 之 version == ver，版號不符時自動覆寫更新；2. 於 plan verify 掃描計畫 .md 若含硬編碼本機絕對路徑 URI 或磁碟機代號發出可攜性警告（第 2 點已於前序計畫完成）
