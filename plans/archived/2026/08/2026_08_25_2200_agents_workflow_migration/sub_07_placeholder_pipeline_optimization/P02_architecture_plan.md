# 架構與模組設計說明書 (Phase 2: Architecture Plan)

> 功能名稱：佔位符解析管線優化 (Placeholder Pipeline Optimization)  
> 建立日期：2026-08-26  
> 所屬主計畫：[2026_08_25_2200_agents_workflow_migration](../umbrella_overview.md)  
> 狀態：Confirmed  
> 模板版本：v1.3  

---

## 1. 模組架構與職責分工 (Module Architecture)

重構 `agents-workflow` 模組內部架構為分層職責模型：

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        CLI 終端介面層 (cli.py)                         │
│  • release (全量已啟用目標發布)                                          │
│  • release-target --list | --add <t> | --remove <t> (目標管理)         │
│  • tokens / list (清冊查詢)                                            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 工廠編譯與發布管線 (compiler.py & publisher.py)         │
│                                                                        │
│  [Stage 1: Content Pipeline]                                           │
│  • 搜集 export / insert / token                                        │
│  • 5-Step 狀態機解算 __@{token}__                                       │
│  • 寫入 cache.root://agents-workflow/resolved_contents/                │
│                                                                        │
│  [Stage 2: Release & Path Pipeline]                                    │
│  • 讀取 release_target 宣告與 config.project.json                      │
│  • 建立 Deployment Manifest Map (Tier 1 拓撲表)                        │
│  • 動態轉譯 __#{uri}__ (Tier 1 ➔ Tier 2 ➔ Tier 3 兜底)                 │
│  • 注入 Header 巨集模板 ({export.description})                         │
│  • 原子 4 步交易：過往清理 ➔ 提前解算 ➔ 持久紀錄 ➔ 目錄落地/軟合併     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  微內核底層設施 (Core URI / Storage)                   │
│  • cache.root:// (中繼快取)                                            │
│  • storage://agents-workflow/release_manifest.json (發布持久紀錄)      │
│  • uri.resolve / os.path.relpath (實體路徑計算與轉譯)                  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心組件與循序流程設計 (Sequence & Data Flow)

### 2.1 6 步管線資料流向 (Pipeline Data Flow)

```text
[assets/{standards,workflows,templates} + contributes.insert]
                           │
                           ▼ (Stage 1: resolve_content)
[cache.root://agents-workflow/resolved_contents/]
                           │
                           ▼ (Stage 2A: release_target 拓撲解析)
[Deployment Manifest Map: source_uri -> dest_abs_path]
                           │
                           ▼ (Stage 2B: resolve_uri 三層重映射)
[Pre-computed Rendered Content Map: dest_abs_path -> final_text]
                           │
                           ▼ (Stage 2C: 4-Step Atomic Release)
1. 清理 storage:// 舊發布檔案
2. 寫入 storage:// 最新清單
3. 原子寫入目標實體目錄 (如 .agents/workflows/, .agents/templates/)
4. 依 enable_agents_md 軟合併 project://AGENTS.md
```

### 2.2 三層 URI 重映射演算邏輯 (URI Resolution Algorithm)

```python
def resolve_uri_tag(tag_uri: str, current_dst_path: str, deployment_map: Dict[str, str]) -> str:
    # 1. Tier 1: 命中本次發布拓撲映射表
    if tag_uri in deployment_map:
        target_dst = deployment_map[tag_uri]
        rel_p = os.path.relpath(target_dst, os.path.dirname(current_dst_path)).replace("\\", "/")
        return rel_p if rel_p.startswith(".") else f"./{rel_p}"

    # 2. Tier 2: 專案級語意協議 (project://, docs://, plans://)
    try:
        real_p = uri.resolve(tag_uri, interactive=False)
        rel_p = os.path.relpath(real_p, os.path.dirname(current_dst_path)).replace("\\", "/")
        return rel_p if rel_p.startswith(".") else f"./{rel_p}"
    except Exception:
        pass

    # 3. Tier 3: 未知/未決協議安全降級
    print(f"[compiler:warning] Unknown or unresolved URI tag: '{tag_uri}'", file=sys.stderr)
    return tag_uri
```

---

## 3. 受影響檔案清單 (Impact Analysis)

### 3.1 程式碼修改清單
- **`source/agents-workflow/manifest.json`**：宣告 `release_target` (`antigravity`)。
- **`source/agents-workflow/config/config.project.json`**：升級為 `"release_targets": ["antigravity"]`。
- **`source/agents-workflow/agents_workflow/compiler.py`**：重構支援兩階段 6 步流水線、快取中繼、三層 URI 重映射與原子發布。
- **`source/agents-workflow/scripts/cli.py`**：實作 `release` 與 `release-target` 系列指令。
- **`source/agents-workflow/assets/`**：全面更新 standards、workflows、templates 中的路徑引用為 `__#{uri}__`。

### 3.2 測試套件更新清單
- **`source/agents-workflow/tests/test_compiler.py`**：新增 6 步管線、三層重映射、Header 巨集插值、原子發布與 CLI 指令單元/整合測試。

---

## 4. 決策紀錄 (Traceability)

- 本架構直接落實 [P01_requirements_spec.md](./P01_requirements_spec.md) 之 FR-01 ~ FR-07 與 EC-01 ~ EC-05。
