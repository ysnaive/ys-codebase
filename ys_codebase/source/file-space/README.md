# `file-space` — [Deprecated] `core.space` 相容轉發空殼模組

> [!IMPORTANT]
> **[Deprecated] 退役與升級通知**：  
> 檔案空間引擎（空間註冊、預設集、組合空間、`YFP2` 單調世代指紋快照、多消費者獨立游標與背景監聽）已全面內聚併入 `module:core`（`core.space`）與 `module:server`（`core-space-watcher`）。  
> 本模組目前僅作 100% 委派 `core.space` 之輕量過渡空殼，無獨立 `watchdog` 依賴與背景服務。  
> **請將 `core` 更新至 `>=1.2.7.5` 並升級下游模組後，執行以下指令移除本模組**：
> ```bash
> python yscb.py remove file-space
> ```

---

## 1. 升級與替代指南 (Migration Guide)

1. **CLI 指令替代**：
   - 請改用 `core` 內建之 `python yscb.py fs <subcmd>` 或 `python yscb.py file-space <subcmd>`：
     ```bash
     python yscb.py fs spaces
     python yscb.py fs status
     python yscb.py fs scan
     python yscb.py fs ls
     python yscb.py fs match <path>
     python yscb.py fs diff --consumer <id> --ack
     python yscb.py fs clean
     ```
2. **Python SDK 替代**：
   - 請將 `import file_space` 替換為 `from core import space` 或 `from core.space import SpaceRegistry, SpaceScanner, consume_diff, subscribe`。
3. **組態設定替代**：
   - 宿主空間定義已由 `ys_codebase/config/file-space/contribute.json` 遷移至 `ys_codebase/config/core/contribute.json`（升級 `core >=1.2.7.5` 時會自動無損轉換合併）。
