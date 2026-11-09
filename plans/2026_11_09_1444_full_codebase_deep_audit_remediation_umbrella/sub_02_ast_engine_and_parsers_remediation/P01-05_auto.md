# 自動連續推進綜合規格與實作紀錄 (Consolidated Auto Plan & Task Log)

> 功能名稱：sub_02_ast_engine_and_parsers_remediation  
> 建立日期：2026-11-09  
> 所屬主計畫：2026_11_09_1444_full_codebase_deep_audit_remediation_umbrella  
> 狀態：Completed  
> 模型：Unknown  
> 依據 P00：[P00_discuss.md](./P00_discuss.md)  
> 模板版本：v1.0  

---

## 1. 需求規格與邊界契約 (P01)

### 1.1 功能需求清單 (Functional Requirements)

| 需求編號 | 需求名稱 | 詳細規格與驗收條件 (Acceptance Criteria) | 優先級 | 對應 P00 語意 |
| :--- | :--- | :--- | :---: | :--- |
| **FR-01** | `GrammarProvisioner` 鎖分離與單飛去重，消除 90 秒跨執行緒凍結 (`AST-AUD-01`) | [`ast/ast_engine/provisioner.py:L143-L232`](https://drive.google.com/file/d/1WD9aPTAgiGblirqRBtM6dIDXRoOgLUoN/view?usp=drivesdk) 將 `load_language` 拆為：鎖內檢查 `_LANGUAGE_CACHE`/`_FAILED_PACKAGES` $\to$ 若需安裝則登記 `_INFLIGHT_EVENTS[lang]` `Event` 並釋放 `cls._LOCK` $\to$ 在鎖外呼叫 `_try_pip_install`（遵守 `_provision_lock` $\to$ `cls._LOCK` 唯一鎖序）$\to$ 重取 `cls._LOCK` 更新快取並喚醒等待者。 | P0 | [P00:DR-01] |
| **FR-02** | 重載符號切片精準定位、跨命名空間基底型別連結與雙軌 ID 空間對齊 (`AST-AUD-02`, `AST-AUD-03`, `ARCH-AST-01`) | 1. [`engine.py:L1375-L1415`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) 之 `_resolve_symbol_node_for_slice` 優先比對 `cand.span.start_line == symbol_or_id.line_number` 與 `fqn`/`short_name`，精準定位同名異載方法。<br>2. [`linker.py:L180-L187, L758-L775, L928-L935`](https://drive.google.com/file/d/1wz1jwCn_jBepZvrAF5Qn0dWLyzvn5BNM/view?usp=drivesdk) 對 `base_types` 同時索引完整限定名與尾端短名，並於 `_expand_contract_from_workspace_graph` 支援重載 `UnifiedSymbol` 對齊 `SymbolNode`；`resolver.py` 支援查詢 `WorkspaceSymbolGraph` 呼叫邊。 | P0 | [P00:DR-01], [P00:DR-03] |
| **FR-03** | 多根空間增量熱修補消歧、鎖保護游標提交、分部符號深拷貝與 Barrel Re-export 不動點迭代 (`AST-AUD-04`, `AST-AUD-05`, `ARCH-AST-04`, `ARCH-AST-06`, `ARCH-AST-07`) | 1. [`bundler.py:L603-L622, L1006-L1024`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) 與 [`engine.py:L646-L648`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) 移除 `if "/" not in rel_key:` 限制，對所有多根同名相對路徑比較實體檔 `mtime`，並支援 `known_indexed_files` 消歧刪除檔。<br>2. `restore_unaggregated_partial_symbol` 深拷貝還原分部符號 (`ARCH-AST-06`)；移除 `bundler.py` 對 `knowledge-db` 組態之反向讀取 (`ARCH-AST-07`)；`ensure_jit_synced` 與 `scripts/hook.core.py` 在 `engine._lock` 與 `consume_diff` 內執行熱修補 (`ARCH-AST-04`)；`linker.py` Pass 2 以最多 8 輪不動點迭代解析多跳 Barrel Re-export 並回填 `_resolved_import_edges`。 | P1 | [P00:DR-01], [P00:DR-03] |
| **FR-04** | C++ 類外定義作用域保留、Python 屬性賦值去重載化、標準庫 Parser 自動降級與 Span/UTF-8 列位移修正 (`AST-AUD-06` ~ `AST-AUD-08`, `ARCH-AST-08`) | 1. [`treesitter.py`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) 與 [`dialects/cpp.py`](https://drive.google.com/file/d/1R9JQ5AFvCVmhcm6aOcI2wC8ETkznXDso/view?usp=drivesdk) 為 C++ `Outer::Inner::method` 保留完整父作用域前綴；對 `field`/`property`/`variable` 停用簽名重載後綴改為同名去重合併。<br>2. [`parsers/registry.py`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk) 當 `TreeSitterDriver` 對 `.py`/`.md` 無法載入語法庫時自動 fallback 至 `PythonASTParser` / `MarkdownParser`。<br>3. [`parsers/base.py`](https://drive.google.com/file/d/1EEGziPF_vPeVDx_NRq8P_aRYeF4Out2l/view?usp=drivesdk) 補齊 `signature`/`parameters`/`return_type`/`doc`/`body` Span、巢狀 `SymbolNode` 樹與 `inherits`/`implements` 邊；[`treesitter.py`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) 支援多行簽名 Span 並以字元長度計算 `end_col`。 | P1 | [P00:DR-02] |
| **FR-05** | 單通解析快取、`SymbolNode` 遞迴凍結、緊湊序列化、快照雙檔讀取鎖與各語言 Parser 邊界收斂 (`AST-AUD-09` ~ `AST-AUD-16`, `ARCH-AST-02`, `ARCH-AST-03`, `S3`) | 1. [`schema.py`](https://drive.google.com/file/d/1BIkbvTvqk2ZyGF9zEJ8vpXTzeH9NAy86/view?usp=drivesdk) 實作遞迴 `_freeze_value` 與 `_thaw_value` (`AST-AUD-14`)，並消除 `FileSymbolGraph` / `WorkspaceSymbolGraph` 重複節點序列化 (`AST-AUD-09`, `ARCH-AST-03`)；[`engine.py`](https://drive.google.com/file/d/15MD9qx01N-2tNf8LfnSzjdahT0e2hG7f/view?usp=drivesdk) `_ensure_loaded_from_disk` 加入 `InterProcessLock` (`AST-AUD-10`)。<br>2. [`parsers/registry.py`](https://drive.google.com/file/d/1YOxfmRa5Sja0fe98WUCdMUNRamFU6UiA/view?usp=drivesdk) 合流器對 `Mapping` 型別 `facets` 執行鍵值聯集 (`AST-AUD-11`)；修正 [`dialects/base.py`](https://drive.google.com/file/d/1MFfZA2sghRNbTnSs0knK9FIaxaZhcBDN/view?usp=drivesdk) `super().field.method()` / `__super` 與 TS `extends_type_clause` (`AST-AUD-12`) 及 [`resolver.py`](https://drive.google.com/file/d/1ZCka6zQPqTIYvg57bty3LL868dS7pOxd/view?usp=drivesdk) fallback 前導 `<kind>` 與泛型 `<...>` 剝離 (`AST-AUD-13`)。<br>3. 消除 [`bundler.py`](https://drive.google.com/file/d/1mTXoeeAVpxVbi3zjGcEX3NFWM4vDBZT6/view?usp=drivesdk) 與 [`treesitter.py`](https://drive.google.com/file/d/1obsGSPSmm0B4Wlr514bqiEUzj7GuipJi/view?usp=drivesdk) 4 倍重複單檔解析 (`ARCH-AST-02`, `AST-AUD-15`)，補齊 [`python_ast.py`](https://drive.google.com/file/d/1bUkUVHJFzGDxa6GvJ5KAzAq5J24t-7lG/view?usp=drivesdk) 巢狀定義與多層呼叫鏈提取 (`AST-AUD-16`)，並修復 `io_utils.py`、`html_parser.py`、`css_parser.py`、`spice_parser.py`、`markdown.py` 邊界與確定性 ID。 | P2 | [P00:DR-01], [P00:DR-02], [P00:DR-03] |

### 1.2 邊界與異常情況 (Edge Cases & Failure Modes)

| 邊界編號 | 情境說明 | 預期防禦與處理行為 |
| :--- | :--- | :--- |
| **EC-01** | 執行緒 A 觸發缺失語言自動 `pip install` 耗時期間，執行緒 B 呼叫已快取語言 `load_language` 或同語言並發請求 | 執行緒 B 零阻塞立即獲得已快取語法；若執行緒 C 同時請求同一缺失語言，則透過 `_INFLIGHT_EVENTS[lang].wait()` 等待執行緒 A 完成而不重複啟動 `pip`。 |
| **EC-02** | 雙根空間（如 `multi_a/sub/mod.py` 與 `multi_b/sub/mod.py`）僅修改其中一檔或刪除其中一檔，或熱修補中途拋出例外 | 增量熱修補透過完整相對路徑、`mtime` 與 `known_indexed_files` 精準匹配目標 Root；若熱修補失敗，`ExitStack` 不提交 `"ast"` 游標，下次 `ensure_jit_synced` 自動重試恢復。 |
| **EC-03** | 在未安裝 `tree_sitter` 套件的離線沙盒環境執行 `ASTEngine` 解析 Python 與 Markdown 檔案 | `ParserRegistry` 自動降級使用 `PythonASTParser` 與 `MarkdownParser`，完整產出 `FileSymbolGraph`、巢狀函式與呼叫邊。 |

### 1.3 非功能需求 (Non-Functional Requirements)

| 需求編號 | 類別 | 指標與量化約束 |
| :--- | :--- | :--- |
| **NFR-01** | 單檔解析延遲 | `TreeSitterDriver` 單通解析快取使熱快取 `_parse_file_full` 加速 $\ge 5\times$（實測 `22.955 ms` $\to$ `3.388 ms`，加速 `6.78x`），`PythonASTParser` 四階段調用由 `80.507 ms` 降至 `44.090 ms`（冷）/ `31.528 ms`（溫）。 |
| **NFR-02** | 記憶體與序列化開銷 | `FileSymbolGraph.to_dict()` 與 `WorkspaceSymbolGraph.to_dict()` 消除重複節點表序列化，序列化 JSON 體積由 `15,388,332 B` 降至 `11,128,636 B`（縮減 `27.68%`），且 `dev check`、`dev test --m ast`、`dev test --m knowledge-db` 100% 通過。 |

### 1.4 知識庫與踩坑紀錄查閱 (Known Gotchas & CAUTIONs)

- **`[!CAUTION]`** Tree-sitter 節點的 `start_point.column` 與 `end_point.column` 單位為 **UTF-8 Byte Offset** 而非 Python 字串的 Unicode Code Point Index！當同一行包含中文字元或 Emoji 時，計算字元列號或切片時必須先以 UTF-8 bytes 切片再 `.decode("utf-8", errors="replace")`。

---

## 2. 架構設計與異動檔案清單 (P02)

### 2.1 模組架構與核心資料流 (Architecture & Data Flow)

- **`GrammarProvisioner` 鎖分離管線**：`cls._LOCK` 僅包裹記憶體字典查找與狀態登記；耗時跨進程鎖 `_provision_lock` 與子進程 `pip install` 移出 `cls._LOCK` 之外，徹底切斷鎖順序反轉。
- **單通解析快取與雙軌圖譜橋接 (`S3`)**：`TreeSitterDriver._get_parsed_unit` 與 `BaseParser._last_base_extract_cache` 讓 `extract_file_graph`、`parse_file`、`extract_call_sites`、`extract_imports` 共享單次解析產物；`WorkspaceSymbolGraph` 與 `CallGraphIndex` 在 `resolver.py` 查詢層無縫協同。

### 2.2 受影響與新建檔案清單 (Impacted & New Files Inventory)

| 檔案路徑 | 類型 | 職責與變更說明 |
| :--- | :---: | :--- |
| `ys_codebase/source/ast/ast_engine/provisioner.py` | Modify | 解耦 `cls._LOCK` 與 `_try_pip_install`，實作 Per-Language `threading.Event` 單飛等待 (`AST-AUD-01`) |
| `ys_codebase/source/ast/ast_engine/io_utils.py` | Modify | `atomic_save_gzip_pickle` 改用顯式 `gzip.GzipFile` 上下文並於 `finally` 清理殘留 `.tmp` 檔 |
| `ys_codebase/source/ast/ast_engine/engine.py` | Modify | 修復重載符號切片定位、`ExitStack` 鎖保護游標提交、多根刪除檔正規化與快照雙檔 `InterProcessLock` 讀取鎖 (`AST-AUD-02`, `AST-AUD-04`, `AST-AUD-10`, `ARCH-AST-04`) |
| `ys_codebase/source/ast/scripts/hook.core.py` | Modify | `on_file_space_changed` 全程持有 `engine._lock` 包裹 `_resolve_consume_diff` 與 `hot_patch_index` (`ARCH-AST-04`) |
| `ys_codebase/source/ast/ast_engine/linker.py` | Modify | 修復限定名基底型別解析、`_expand_contract_from_workspace_graph` 重載映射與 Pass 2 Barrel Re-export 8 輪不動點迭代 (`AST-AUD-03`, `AST-AUD-05`) |
| `ys_codebase/source/ast/ast_engine/bundler.py` | Modify | 實作 `restore_unaggregated_partial_symbol` 深拷貝、移除 `knowledge-db` 組態反向依賴、含 `/` 相對路徑 `mtime` 消歧、`LanguageConfig` 完整欄位檢查與檔案清單快取復用 (`AST-AUD-04`, `AST-AUD-05`, `AST-AUD-15`, `ARCH-AST-06`, `ARCH-AST-07`) |
| `ys_codebase/source/ast/ast_engine/schema.py` | Modify | 遞迴凍結/解凍 `facets` 容器，並消除 `FileSymbolGraph`/`WorkspaceSymbolGraph` 重複節點序列化 (`AST-AUD-09`, `AST-AUD-14`, `ARCH-AST-03`) |
| `ys_codebase/source/ast/ast_engine/resolver.py` | Modify | 修復 `SymbolSelector.parse` fallback 分支前導 `<kind>` 與泛型 `<...>` 剝離，並支援查詢 `WorkspaceSymbolGraph` (`AST-AUD-13`, `ARCH-AST-01`) |
| `ys_codebase/source/ast/ast_engine/parsers/treesitter.py` | Modify | 實作 `_get_parsed_unit` 單通快取、修復 C++ `Outer::Inner::method` 作用域、Python 屬性去重載化、多行簽名 Span/UTF-8 列號、合流器 `Mapping` 聯集與 TS `extends_type_clause` (`ARCH-AST-02`, `AST-AUD-06`, `AST-AUD-08`, `AST-AUD-11`, `AST-AUD-12`) |
| `ys_codebase/source/ast/ast_engine/parsers/registry.py` | Modify | 當 `TreeSitterDriver` 不可用時自動降級至 `PythonASTParser`/`MarkdownParser`，修復合流器 `Mapping` `facets` 聯集並復用 BaseParser 單通快取 (`AST-AUD-07`, `AST-AUD-11`, `ARCH-AST-02`) |
| `ys_codebase/source/ast/ast_engine/parsers/base.py` | Modify | 修復 `convert_legacy_symbols_to_file_graph` 階層樹、`signature`/`parameters`/`return_type`/`doc`/`body` Span 與 `inherits`/`implements` 邊及單通快取 (`AST-AUD-08`, `ARCH-AST-02`, `ARCH-AST-08`) |
| `ys_codebase/source/ast/ast_engine/parsers/python_ast.py` | Modify | 支援單通 AST 快取、函式內巢狀定義提取、類別欄位與任意深度屬性呼叫鏈提取 (`AST-AUD-16`, `ARCH-AST-08`) |
| `ys_codebase/source/ast/ast_engine/parsers/{html_parser,css_parser,spice_parser,markdown}.py` | Modify | 修復單行多段/未閉合註解、巢狀/未閉合 `.SUBCKT`、Setext 標題與確定性無碰撞符號 ID |
| `ys_codebase/source/ast/ast_engine/dialects/{base,cpp}.py` | Modify | 修正 `normalize_call_receiver` 對 `super().field.method()` / `__super` 的處理及 C++ 巢狀類外作用域拆解 (`AST-AUD-06`, `AST-AUD-12`) |
| `ys_codebase/source/ast/tests/{test_provisioner_and_jit,test_dialects_and_parsers,test_overload_and_topology}.py` | Modify | 新增並發單飛鎖、游標事務回滾、分部深拷貝、多根消歧、C++ 巢狀作用域、多跳 Barrel Re-export、泛型選擇器與重載 `slice_part` 單元測試 |

### 2.3 架構決策記錄 (Architecture Decision Records)

- **[P02:DR-01] `FileSymbolGraph` 與 `WorkspaceSymbolGraph` 去重序列化 (`AST-AUD-09`, `ARCH-AST-03`)**：`FileSymbolGraph.to_dict()` 僅序列化未包含於 `root_nodes` 子樹之獨立節點，於 `from_dict()` 透過 `_walk_nodes(root_nodes)` 單次重建 `all_nodes_by_id`；`WorkspaceSymbolGraph.to_dict()` 僅序列化未包含於 `file_graphs` 之獨立節點，於 `__post_init__` 自動重建完整 `nodes_by_id` 與出入邊索引。

---

## 3. 介面契約與 API 簽名 (P03)

### 3.1 介面契約與核心簽名 (Interface Inventory & Method Signatures)

```python
# ys_codebase/source/ast/ast_engine/provisioner.py
class GrammarProvisioner:
    @classmethod
    def load_language(
        cls,
        lang_key: str,
        module_name: str,
        entry_func: str = "language",
        auto_install_pkg: Optional[str] = None,
        attempt_auto_install: bool = True,
    ) -> Optional[Any]: ...

# ys_codebase/source/ast/ast_engine/schema.py
def _freeze_value(val: Any) -> Any: ...
def _thaw_value(val: Any) -> Any: ...
def _freeze_facets_dict(raw_facets: Optional[Mapping[str, Any]]) -> Mapping[str, Any]: ...
```

- **錯誤與例外契約 (Error & Exception Contracts)**：
  - `GrammarProvisioner.load_language` 在離線或 `pip install` 失敗時記錄 warning 並優雅回傳 `None`，絕不拋出未捕獲例外或永久卡死鎖。
  - `SymbolNode.to_dict()` 對任意深度之巢狀 `MappingProxyType` / `tuple` / `frozenset` 100% 轉為 JSON 相容之 `dict` / `list`。
- **階段決策紀錄**：[P03:DR-01] 保持 `ASTEngine`、`WorkspaceSymbolGraph`、`SymbolNode` 與 `len(ast_engine.__all__) == 72` 公開介面 100% 向下相容。

---

## 4. 定稿審查與文檔衝擊規劃 (P04)

### 4.1 交叉驗證與靈魂拷問 (Cross-Validation & Resilience Review)

- **需求對齊**：FR-01 ~ FR-05 完整覆蓋 `AST-AUD-01` ~ `AST-AUD-16` 全部 16 項審計問題與 `ARCH-AST-01` ~ `ARCH-AST-08`（Surgery `S3`）。
- **邊界防護**：EC-01 ~ EC-03 涵蓋並發安裝、多根空間同名檔、熱修補異常游標回滾與無 `tree-sitter` 純標準庫環境。
- **依賴純淨**：100% 符合 NFR-01 與 NFR-02，且移除 `ast` 對 `knowledge-db` 組態之反向耦合。
- **靈魂拷問與防護解法**：若 `_try_pip_install` 執行期間拋出未預期例外，`try...finally` 保證於 `cls._LOCK` 內清除 `_INFLIGHT_EVENTS.pop(cache_key, None)` 並呼叫 `inflight_event.set()`，防止等待該 Event 的其他執行緒永久死鎖。

### 4.2 知識庫文檔衝擊與交付規劃 (Documentation Impact Plan)

| 維度 | 文件路徑 | 變更類型 | 交付內容與重點 |
| :--- | :--- | :---: | :--- |
| **模組手冊** | `ys_codebase/source/ast/README.md` | N/A | 內部穩定性與單通解析效能優化，公開 CLI/SDK 契約不變 |
| **專題手冊** | `docs/ast/architecture.md` | N/A | 內部修復，四階段管線契約不變 |
| **設計決策** | `docs/ast/DESIGN_NOTES.md` | N/A | 已記錄於 `P07_walkthrough.md` 與 ADR |
| **微觀註解** | 源碼檔案 Docstrings | Modify | 更新 `provisioner.py`、`linker.py`、`bundler.py`、`treesitter.py`、`schema.py` Docstrings |
| **發布日誌** | `changelog.md` | Modify | 記錄 `sub_02` 實作、基準實測與驗證結果 |

- **決策定稿**：**[P04:DR-01]** 確認 `sub_02` 規格定稿並完成實作驗證閉環。

---

## 5. 實作任務清單與偏差紀錄 (P05)

### 5.1 實作任務清單 (Task Breakdown)

- [x] **TASK-01**：實作 `FR-01`（`provisioner.py` 解耦 `cls._LOCK` 與 `_try_pip_install`，加入 Per-Language `Event` 單飛等待，`AST-AUD-01`）
- [x] **TASK-02**：實作 `FR-02` 與 `FR-03`（`engine.py` 重載切片定位與 `ExitStack` 鎖保護游標提交、`scripts/hook.core.py` 鎖保護、`linker.py` 限定名基底與雙軌 ID 映射、Pass 2 不動點迭代，以及 `bundler.py` 分部深拷貝、移除 `knowledge-db` 依賴、多根 `mtime` 消歧與完整 `LanguageConfig` 檢查，`AST-AUD-02` ~ `AST-AUD-05`, `ARCH-AST-01`, `ARCH-AST-04`, `ARCH-AST-06`, `ARCH-AST-07`）
- [x] **TASK-03**：實作 `FR-04`（C++ `Outer::Inner::method` 作用域、Python 屬性去重載化、`registry.py` 標準庫 Parser 自動降級、`base.py` 與 `treesitter.py` 單通解析快取與 Span/UTF-8 列號修正，`AST-AUD-06` ~ `AST-AUD-08`, `ARCH-AST-02`, `ARCH-AST-08`）
- [x] **TASK-04**：實作 `FR-05`（`schema.py` 遞迴凍結與序列化去重、`engine.py` 快照雙檔讀取鎖、合流交換律、`dialects/base.py` 與 `resolver.py` 修正、`python_ast.py` 巢狀定義提取，以及 `io_utils.py`/`html_parser.py`/`css_parser.py`/`spice_parser.py`/`markdown.py` 邊界修復，`AST-AUD-09` ~ `AST-AUD-16`, `ARCH-AST-03`）
- [x] **TASK-05**：補齊 `test_provisioner_and_jit.py`、`test_dialects_and_parsers.py`、`test_overload_and_topology.py` 單元測試，同步 `.modules/ast` 並重打包 `.build/ast` 與 `release/ast`，執行 `python3 -W error::ResourceWarning yscb.py dev check`、`dev test --m ast`（52/52 通過）與 `dev test --m knowledge-db`（113/113 通過）驗證 100% 通過

### 5.2 實作偏差紀錄表 (Implementation Deviations)

| 任務編號 | 偏差等級 | 偏離描述與決策理由 | 處置方式 / 記錄 |
| :--- | :---: | :--- | :--- |
| **TASK-01 ~ TASK-05** | None | 完全依循 `R01`、`R02`（Surgery `S3` & `ARCH-AST-01~08`）與 `P01-05` 規格落地，零架構或介面偏差 | 已驗證 100% 通過 |
