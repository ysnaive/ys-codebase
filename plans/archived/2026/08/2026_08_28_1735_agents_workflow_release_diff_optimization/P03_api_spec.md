# API 與介面規格書 (API & Interface Specification)

> 功能名稱：agents-workflow 發布引擎來源 Diff 檢測與無效 File IO 優化 (agents-workflow Release Diff Optimization)  
> 建立日期：2026-08-28  
> 所屬主計畫：無（獨立計畫）  
> 狀態：Confirmed  
> 模板版本：v1.2  

---

## 1. 介面契約清單 (Interface Inventory)

| 介面 / 類別名稱 | 所屬檔案路徑 | 存取層級 | 核心職責 |
| :--- | :--- | :---: | :--- |
| `ReleasePublisher` | `source/agents-workflow/agents_workflow/publisher.py` | Public | 發布引擎類別，負責來源指紋計算、兩階 Diff 判斷、發布拓撲物化與軟合併。 |
| `compute_source_fingerprint` | `source/agents-workflow/agents_workflow/publisher.py` | Internal | 計算來源資源、組態與 Target 規則之綜合 SHA-256 特徵指紋。 |
| `release_all` | `source/agents-workflow/agents_workflow/publisher.py` | Public | 執行發布流水線，支援 `force` 強制模式與詳細指標回傳。 |
| `_soft_merge_agents_md` | `source/agents-workflow/agents_workflow/publisher.py` | Internal | 執行 AGENTS.md 軟合併注入，具備內容差異檢測與跳過寫入機制。 |
| `release` (CLI Subcommand) | `source/agents-workflow/scripts/cli.py` | Public | 命令列發布進入點，支援 `--force` 旗標。 |
| `on_reload` | `source/agents-workflow/scripts/hook.core.py` | Public | 微核心 Stage 4 reload 監聽 Hook，輸出結構化統計日誌。 |

---

## 2. 核心 API 簽名與詳細規格 (Method Signatures & Contracts)

### 2.1 `ReleasePublisher.compute_source_fingerprint`
```python
def compute_source_fingerprint(self) -> str:
    """
    計算來源端綜合特徵指紋 (SHA-256 Hex Digest)。
    
    涵蓋維度：
    1. 所有 assets/ 資源檔案 (templates, standards, workflows) 之路徑、mtime、size 及 SHA-1。
    2. manifest.json 實體檔案之 mtime、size 及 SHA-1。
    3. config.project.json 設定檔之內容 (release_targets, enable_agents_md 等)。
    4. 所有已啟用 release_targets 之 projections 與 Header 模板定義。
    
    Returns:
        str: 64 位元 SHA-256 綜合指紋字串。
    """
```

### 2.2 `ReleasePublisher.release_all`
```python
def release_all(self, force: bool = False, interactive: bool = False) -> Dict[str, Any]:
    """
    執行 4 步原子發布交易流水線（支援雙階 Diff 優化）：
    
    Stage 0: 來源指紋提前短路檢查 (若 not force 且指紋相符且目標檔案皆存在，立即返回)
    Stage 1: 內容佔位符展開 (compile_stage1)
    Stage 2: 發布拓撲解算與 URI 佔位符轉譯 (resolve_stage2_uri)
    Stage 3: 持久化 release_manifest.json (記錄新 fingerprint 與 published_files)
    Stage 4: 落地端檔案內容比對與增量物化 (僅在內容相異或 force=True 時寫入磁碟)
    
    Args:
        force (bool): 是否強制忽略所有 Diff 檢測進行全量重新編譯與覆寫。預設 False。
        interactive (bool): 是否處於互動模式。預設 False。
        
    Returns:
        Dict[str, Any]:
            {
                "success": bool,
                "short_circuited": bool,    # 是否觸發 Stage 0 短路
                "published_count": int,     # 納管發布檔案總數
                "written_count": int,       # 實體寫入磁碟之檔案數
                "skipped_count": int,       # 內容無變化而跳過寫入之檔案數
                "removed_count": int,       # 本次清理之過往孤立檔案數
                "active_targets": List[str],# 已啟用發布目標清單
                "orphan_targets": List[str],# 未註冊之孤立目標清單
                "error": Optional[str]      # 失敗錯誤訊息 (若有)
            }
    """
```

### 2.3 `ReleasePublisher._soft_merge_agents_md`
```python
def _soft_merge_agents_md(self, dev_standards_content: str, proj_root: str, force: bool = False) -> Tuple[bool, bool]:
    """
    執行 AGENTS.md 軟合併注入，保留自定義章節。
    
    Args:
        dev_standards_content (str): 待注入的標準規範內容。
        proj_root (str): 專案根目錄絕對路徑。
        force (bool): 是否強制覆寫。預設 False。
        
    Returns:
        Tuple[bool, bool]: (success, written) - 是否成功、是否發生實體寫入。
    """
```

### 2.4 CLI 命令列與 Hook 規格
- **CLI**：`python yscb.py agents-workflow release [--force]`
- **Hook 日誌格式**：
  - 短路時：`[agents-workflow:hook] Auto-release skipped on reload (no changes detected, {skipped_count} files up to date).`
  - 有發布時：`[agents-workflow:hook] Auto-released on reload ({written_count} written, {skipped_count} unchanged, {removed_count} removed).`

---

## 3. 依賴拓撲與實作順序 (Implementation Topology)

```text
[1] ReleasePublisher 核心升級 (source/agents-workflow/agents_workflow/publisher.py)
      ├─► compute_source_fingerprint() 實作
      ├─► _soft_merge_agents_md() 升級 (Diff 檢測與 (success, written) 回傳)
      └─► release_all(force) 實作 (Stage 0 短路 + Stage 4 內容比對 + 結構化指標)
            │
            ▼
[2] CLI 指令介面擴充 (source/agents-workflow/scripts/cli.py)
      └─► 為 release 命令加入 --force 參數支援
            │
            ▼
[3] 微核心 Hook 日誌優化 (source/agents-workflow/scripts/hook.core.py)
      └─► on_reload() 接收結構化指標並格式化輸出
            │
            ▼
[4] 單元與整合測試套件 (source/agents-workflow/tests/test_publisher.py)
      └─► 實作 FT-01~06, ET-01~03 與回歸驗證
```
