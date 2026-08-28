# YSCB CLI 指令防呆與語意情境對照指南 (Agents CLI Guild)

<!-- YSCB_AGENTS_CLI_GUILD_BEGIN -->
| 指令名稱 | 推薦/適用情境 (Pros) | 🚨 絕對禁止/不適用情境 (Cons) |
| :--- | :--- | :--- |
| **`python yscb.py install`** | ✅ 安裝新模組能力至環境中<br/>✅ 本地模組自引用調試: install <mod>@build --force (不更新無關模組) | 🚨 嚴禁未經開發者指示在日常開發中重複安裝或重裝全部模組 |
| **`python yscb.py reload`** | ✅ 重新聚合 contributes 並觸發模組 on_reload Hook | *(無特殊禁止事項)* |
| **`python yscb.py remove`** | ✅ 清理不再使用之模組 | 🚨 嚴禁擅自移除 core 或使用中之依賴模組 |
| **`python yscb.py rollback`** | ✅ 當前環境損毀時回滾至前一快照 | 🚨 嚴禁未經確認擅自回滾環境 |
| **`python yscb.py update`** | ✅ 升級已安裝之模組版本 | 🚨 嚴禁在未獲升級指示前擅自更新 |
| **`python yscb.py uri`** | ✅ 動態解析語意 URI (如 python yscb.py uri resolve project://AGENTS.md) | *(無特殊禁止事項)* |
| **`python yscb.py agents-workflow compile`** | ✅ 測試編譯或除錯 Stage 1 中繼資產 | *(無特殊禁止事項)* |
| **`python yscb.py agents-workflow init`** | ✅ 專案初次建立或重新初始化 agents-workflow 工作流環境 | 🚨 嚴禁在已有工作流配置的環境重複手動執行 init |
| **`python yscb.py agents-workflow list`** | ✅ 檢視當前環境已安裝之模組清冊與版本<br/>✅ 檢視 agents-workflow 導出之規範、工作流與模板清單 | *(無特殊禁止事項)* |
| **`python yscb.py agents-workflow plan`** | ✅ 檢視計畫狀態: agents-workflow plan status<br/>✅ 搜尋歷史計畫: agents-workflow plan search <query><br/>✅ 驗證計畫完整度: agents-workflow plan verify<br/>✅ 依開發者明確指示封存計畫: agents-workflow plan archive <plan_dir> | 🚨 嚴禁 Agent 主動或擅自執行 plan archive (除非開發者明確指示歸檔) |
| **`python yscb.py agents-workflow release-target`** | ✅ 檢視或管理工作流發布目標清冊 | *(無特殊禁止事項)* |
| **`python yscb.py agents-workflow tokens`** | ✅ 檢視全系統可用的 Token 錨點清單 | *(無特殊禁止事項)* |
| **`python yscb.py dev build`** | ✅ 手動打包本地測試包供跨環境測試或本地直裝物化 | 🚨 嚴禁在執行 dev test 前手動執行 dev build (dev test 內部自動前置構建) |
| **`python yscb.py dev bump-major`** | ✅ 架構不相容重大升版 | 🚨 未獲指示前絕對禁止擅自執行 |
| **`python yscb.py dev bump-minor`** | ✅ 向下相容新功能升版 | 🚨 未獲指示前絕對禁止擅自執行 |
| **`python yscb.py dev bump-patch`** | ✅ 向下相容 Bug 修復升版 | 🚨 未獲指示前絕對禁止擅自執行 |
| **`python yscb.py dev bump-revision`** | ✅ 工程微調/文檔修訂升版 | 🚨 未獲指示前絕對禁止擅自執行 |
| **`python yscb.py dev check`** | ✅ 代碼編寫完成後進行靜態合規與語法預檢 (Phase 5 交付前) | 🚨 嚴禁未修改代碼即無意義高頻重複執行 |
| **`python yscb.py dev create`** | ✅ 建立新模組骨架目錄結構 (source/<name>) | 🚨 嚴禁未經確認在非源碼目錄或非標準路徑建立模組 |
| **`python yscb.py dev release`** | ✅ 模組通過測試後編譯發布工作流資產至各 release_target (如 .agents/)<br/>✅ 模組通過全部測試，正式打包發布 (Phase 7 結案前) | 🚨 嚴禁在未獲發布授權前擅自執行<br/>🚨 開發者未明確下達發布指示前絕對禁止執行 |
| **`python yscb.py dev release-check`** | ✅ 發布前預檢 3-Gate 合規性 | *(無特殊禁止事項)* |
| **`python yscb.py dev release-git`** | ✅ 發布完成後進行本地 git commit 與 tag (🚨 嚴禁遠端 push) | 🚨 未獲指示前絕對禁止擅自執行<br/>🚨 嚴禁執行 git push 遠端同步 |
| **`python yscb.py dev test`** | ✅ 正在開發當前模組，需驗證單元邏輯或整體功能 (Phase 5/6)<br/>✅ 微調時優先附加 --no-build 或 -k <pattern> 快速跑測 | 🚨 嚴禁在跑測前手動執行 dev build<br/>🚨 嚴禁在日常開發中執行 dev test --all (僅全系統回歸或顯式指示時調用)<br/>🚨 嚴禁調用內部原子操作 dev op-test |
| **`python yscb.py knowledge-db bundle`** | ✅ 建置與發布空間之 SemanticBundle 發布包 | 🚨 僅查詢檢索時無需重複完整打包 |
| **`python yscb.py knowledge-db clean`** | ✅ 快取異常損毀或需要徹底重建資料庫時 | 🚨 日常常規操作無需隨意清理快取 |
| **`python yscb.py knowledge-db index`** | ✅ 預熱檢索快取加速大規模檢索 | 🚨 檢索 search 指令已內建自動懶索引建置 |
| **`python yscb.py knowledge-db scan`** | ✅ 比對程式碼與文檔變更並更新指紋庫 | 🚨 測試期間無需頻繁手動掃描 |
| **`python yscb.py knowledge-db search`** | ✅ 透過關鍵字、符號名稱或功能描述快速定位代碼與文檔 | 🚨 單純檢視空間清單時請用 status |
| **`python yscb.py knowledge-db status`** | ✅ 環境健康診斷與自我修復檢查<br/>✅ 日常檢視知識庫已註冊空間與快取狀態 | 🚨 執行大量資料庫重構或打包時 |
<!-- YSCB_AGENTS_CLI_GUILD_END -->

---

## 🚨 Agent CLI 調用紀律與強制守門原則 (CLI Execution Discipline)

所有 Agent 在執行任何 `python yscb.py` 宿主指令或子模組指令前，**必須嚴格遵循以下守門規範**：

1. **查表比對 (Look Up & Match)**：
   - 欲執行指令前，必須先比對本指南中的「語意情境與指令防呆對照表」。
   - 僅當當前開發意圖 **100% 契合 `✅ 推薦/適用情境`** 時，方可直接執行。

2. **Default-Deny 閉環與未列情境阻斷**：
   - 若欲執行之指令或參數組合 **未列於對照表中**、**無對應推薦欄位**、或 **命中 `🚨 絕對禁止/不適用情境`**：
     - **Agent 絕對禁止自行拼裝或擅自執行！**
     - 必須立即發起 `/Discuss` 向開發者呈遞：
       1. **調用意圖**（為什麼需要執行此指令？欲解決什麼問題？）。
       2. **預期完整命令列**（欲執行的確切命令與參數）。
     - 只有在開發者明確回覆允許或授權後，方可執行該指令。

3. **常用測試與除錯極速指南**：
   - 當前模組開發跑測：`python yscb.py dev test <mod>`（嚴禁先手動 build，嚴禁跑 `--all`）。
   - 當前模組單元快速跑測：`python yscb.py dev test <mod> --no-build`。
   - 單一測試案例正則篩選：`python yscb.py dev test <mod> -k <pattern>`。
   - 本地自引用調試安裝：`python yscb.py install <mod>@build --force`（嚴禁未經指示重新安裝全系統）。
   - 版本號遞增：**必須等待開發者明確指示升版類型後方可執行**。
