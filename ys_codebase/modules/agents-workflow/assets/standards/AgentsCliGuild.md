# YSCB CLI 指令防呆與語意情境對照指南 (Agents CLI Guild)

<!-- YSCB_AGENTS_CLI_GUILD_BEGIN -->
`__@{AGENTS_CLI_GUILD}__`
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
