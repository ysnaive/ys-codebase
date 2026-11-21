# 子模組架構設計規格：`core.surface.cli`（靜態索引命令列轉接與雙軌輸出草案）

> **所屬功能域**：`Domain 6 — 對外門面域 (surface/)`
> **模組路徑**：`core_v2/source/core/core/surface/cli/`（規劃中）
> **依賴上限（Allowed Imports）**：`foundation/*`、`execution.runtime`、`surface.sdk`
> **禁止反向依賴（Forbidden Imports）**：嚴禁於冷啟動 `--help` 或參數驗證期間匯入任何 `module://` 業務源碼
> **狀態**：`Draft`（排入 Wave 1.2 實作；Schema 原語 `Arg`、`Option` 與 `format_output` 已先於 `core.surface.sdk` 落地）

## 1. 模組定位與職責邊界 (Positioning & Scope)

`core.surface.cli` 負責 Domain 6 面向終端機之極薄命令列轉接層（`core/surface/cli/`），統一接管命令列參數解析、基於靜態索引的 `--help` 說明卡片渲染、輸出序列化（`--json` 與人類排版雙軌分流）以及經由 `RuntimeDispatcher` 發起之 `CallerSurface.CLI` 呼叫，確保下游業務模組完全免除 CLI 解析與輸出樣板碼。

## 2. 消費自 `core.surface.sdk` 之 Schema 與輸出原語

| 符號 | 來源 | CLI 層職責 |
| :--- | :--- | :--- |
| `Arg(summary, name)` | `core.surface.sdk` | 自 `typing.Annotated[T, Arg(...)]` 萃取位置參數定義 |
| `Option(short, summary, long_name)` | `core.surface.sdk` | 自 `typing.Annotated[T, Option(...)]` 萃取 `--long` / `-s` 具名選項 |
| `HumanRenderable` | `core.surface.sdk` | 選配 `render_text() -> str` 協定，提供非 `--json` 模式下之人類可讀排版 |
| `ExitCodeProvider` | `core.surface.sdk` | 選配 `exit_code() -> int` 協定，直接映射至行程語意退出碼（預設 `0`） |
| `format_output(output)` | `core.surface.sdk` | 非 `--json` 模式下統一萃取 `(rendered_text, exit_code)` |

### CLI DTO 註解綁定規則
1. 標註 `Arg` 之位置欄位依宣告順序綁定；`name` 省略時預設沿用 Dataclass 欄位名稱。
2. 標註 `Option` 之具名欄位綁定 `--<long_name>`（省略時預設轉為 kebab-case 欄位名）與選配 `-<short>` 短旗標。
3. 未標註 `Arg` 之純量 `bool` 欄位映射為 `--flag` / `--no-flag` 布林開關；尾端帶 `Arg` 之 `Sequence[T]` 欄位接收可變長位置參數。

## 3. 規劃之命令路由與全域統一旗標（Wave 1.2）

- **零匯入靜態路由探測**：直讀 `<workspace_root>/.cache/tasks.index.json`（由 `packaging` / `dev 2.0` 編譯產出）組建指令樹、`--help` 卡片與別名查詢（`CliBindingSpec.command_path` / `aliases`），於 `--help` 或未知指令拼寫建議期間零載入任何模組 Python 代碼。
- **入口統一接管旗標**：
  - `--help` / `-h`：依靜態路由與 DTO Schema 渲染模組／群組／任務摘要、位置參數與選項清單並以退出碼 `0` 結束。
  - `--json`：經 `DataclassCodec.encode` 直接於 `stdout` 輸出嚴格 JSON 化之 `TaskOutcome`（`ok`、`value`、`error`），壓制 `HumanRenderable.render_text()`，同時保留 `ExitCodeProvider.exit_code()` 或錯誤碼映射。
  - `--cold`：強制於 `InvokeRequest` 注入 `ClientRoutingPolicy.FORCE_COLD`，覆寫 `@task(dispatch_mode=...)` 預設路由以執行冷啟動隔離派發。
- **TTY 與安全守門**：互動式標準輸入提示與 `SecurityTier.GATED` 破壞性授權確認僅於 CLI 邊界（`CallerSurface.CLI`）進行，通過確認後填寫 `approval_scope` 再送交 `RuntimeDispatcher.invoke`。

```text
argv -> 解析入口統一旗標 (--help / --json / --cold)
     -> 透過 tasks.index.json 解析 command_path 與父層範圍別名
     -> 依任務 Input DTO (Arg / Option) 解碼其餘參數
     -> 建立 InvokeRequest(caller_surface=CallerSurface.CLI, ...)
     -> 經 RuntimeDispatcher 派發 -> format_output / --json -> sys.exit(code)
```

## 4. 依賴邊界與轉正門檻

- 冷啟動 `--help` 渲染與參數驗證階段嚴禁匯入任何 `module://` 業務代碼。
- 僅允許依賴 `core.foundation`、`core.execution.runtime` 與 `core.surface.sdk` 公開門面。
- 自 `Draft` 晉升為 `Active` 須待 Wave 1.2 鎖定 `tasks.index.json` Schema 並納入 `verify_execution_live.py` Gate 0 1:1 活規格校驗。
