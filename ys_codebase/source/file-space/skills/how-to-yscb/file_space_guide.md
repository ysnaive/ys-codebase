### `file-space` (多工作空間幾何路由與變更指紋引擎)

- **核心定位**：統一管理生態系多工作空間 (`source`, `docs`, `plans` 等) 之目錄 URI 映射、雙階段增量指紋快照 (`YFP2`)、Merkle Root 完整性摘要與多消費者獨立游標 (`CursorStore`)。
- **常用指令**：
  - `python yscb.py file-space status [--space <name>] [--json]`：檢視已註冊空間、檔案數、`head_generation`、`merkle_root` 與消費者游標狀態。
  - `python yscb.py file-space scan [--space <name>] [--force] [--json]`：執行雙階段增量指紋掃描並更新 `YFP2` 快照。
  - `python yscb.py file-space files [--space <name>] [--pattern <glob>] [--json]`：列舉空間內受納管之有效檔案清單。
  - `python yscb.py file-space diff [--space <name>] [--consumer <id>] [--ack] [--json]`：查詢特定消費者游標相對於最新世代之增量變更集。
  - `python yscb.py file-space clean [--space <name>] [--consumer <id>] [--json]`：清除二進位指紋快照或重置特定消費者游標。
