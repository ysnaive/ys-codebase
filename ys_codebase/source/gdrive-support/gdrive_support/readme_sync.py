"""
Root and managed repository README.md soft-merge, soft-remove, and local state cache helpers.
"""
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional, Tuple

from core import uri
from core import vfs

from .config import GDriveConfig, normalize_remote_rel_path
from .transport import AbstractSyncTransport

DEFAULT_REPO_SYNC_ROOT = "repo"
REPO_README_FILENAME = "README.md"
ROOT_README_BEGIN_MARKER = "<!-- === YSCB GDRIVE REPO_SYNC BEGIN === -->"
ROOT_README_END_MARKER = "<!-- === YSCB GDRIVE REPO_SYNC END === -->"


def _extract_cached_readme_state(raw_entry: Any) -> Tuple[Optional[bool], str]:
    """Normalize a stored readme_sync_state entry (legacy bool or dict) into (enabled, repo_sync_root)."""
    if isinstance(raw_entry, bool):
        return raw_entry, DEFAULT_REPO_SYNC_ROOT
    if isinstance(raw_entry, dict) and "enable" in raw_entry:
        return (
            bool(raw_entry["enable"]),
            normalize_remote_rel_path(
                str(raw_entry.get("repo_sync_root") or DEFAULT_REPO_SYNC_ROOT)
            )
            or DEFAULT_REPO_SYNC_ROOT,
        )
    return None, DEFAULT_REPO_SYNC_ROOT


def build_managed_readme_content(repo_sync_root: str = DEFAULT_REPO_SYNC_ROOT) -> str:
    """Generate the standard README.md placed at <root_folder_id>/<repo_sync_root>/README.md."""
    norm_root = normalize_remote_rel_path(repo_sync_root) or DEFAULT_REPO_SYNC_ROOT
    return (
        f"# YS-Codebase Google Drive Managed Sync Repository (`{norm_root}/`)\n\n"
        "> **[!IMPORTANT] 自動化託管聲明**\n"
        f"> 本 `{norm_root}/` 資料夾由 `yscb module:gdrive-support` (`yscb gdrive`) 自動管理。\n\n"
        "## 1. 目錄結構規範\n\n"
        "- `.yscb_gdrive.json`：倉庫身分證、分支註冊表與跨分支引用索引（**請勿手動刪除或修改**）。\n"
        "- `main/`：完整主幹分支（存放 100% 真實資料夾與最新完整實體檔案）。\n"
        "- `<branch>/`（如 `v1.0`, `v1.5`）：差量版本分支（真實資料夾骨架 + 差異實體檔 + 指向未修改檔案之 Google Drive Shortcut）。\n"
        "- `.history/`：存放被更新替換下來、但仍受舊分支 Shortcut 引用之凍結版本實體檔（當無任何分支引用時自動移入 Google Drive 原生 30 天垃圾桶）。\n"
        "- `.trash/`：專供無原生垃圾桶權限之外部/網頁版 AI 搬移待刪除檔案的暫存緩衝區（**注意：本地 `yscb gdrive` 同步或分支操作時會自動清空 `.trash/` 內的所有項目並移入 Google Drive 原生 30 天垃圾桶，切勿將 `.trash/` 當作長期備份資料夾！**）。\n\n"
        "## 2. 人類與外部/網頁版 AI Agent 操作注意事項\n\n"
        f"1. **修改前先確認目標分支（直接改 `main/` vs. 新增雲端分支 `{norm_root}/<new_branch>/`）**：外部 Agent 於寫入前應先向使用者確認要直接更新 `main/` 或是建立新分支 `{norm_root}/<new_branch>/`（本地 `yscb gdrive` 支援自動發現雲端新建之分支資料夾，無須手動修改 `.yscb_gdrive.json`）。\n"
        f"2. **更新既有檔案時**：若無法直接覆寫原檔案版本（例如透過網頁版 Gemini 操作），請**先將原檔案或原 Shortcut 移動至 `{norm_root}/.trash/` 資料夾，再於原路徑建立更新後的檔案**（本地同步時會自動幫你把 `{norm_root}/.trash/` 內的舊檔轉移至 Google Drive 原生 30 天垃圾桶）。\n"
        "3. **保持原檔案類型**：請直接上傳/建立原始檔案格式（如 `.md`, `.json`, `.py`, `.xlsx`, `.pdf`），勿轉換為雲端專屬線上文件格式。\n"
        "4. **切勿直接修改 `.history/` 內之檔案**：`.history/` 專供保護歷史分支版本凍結完整性。\n"
    )


def build_root_readme_managed_block(repo_sync_root: str = DEFAULT_REPO_SYNC_ROOT) -> str:
    """Generate the managed block injected into the top-level <root_folder_id>/README.md when repo_sync.enable is True."""
    norm_root = normalize_remote_rel_path(repo_sync_root) or DEFAULT_REPO_SYNC_ROOT
    return (
        f"{ROOT_README_BEGIN_MARKER}\n"
        f"## YS-Codebase Cloud Root & `{norm_root}/` Managed Notice (`yscb module:gdrive-support`)\n\n"
        f"- **純雲端自由儲存區 (`<root>/*`，不含 `{norm_root}/`)**：\n"
        f"  - 位於本根目錄（`{norm_root}/` 以外）的所有資料夾與檔案屬於**不拉到本地自動同步之純雲端儲存區**，供開發者或 Agent 透過原子指令（`yscb gdrive ls / get / put / mkdir / rm`）按需單點存取。\n"
        f"- **受控分支同步倉 (`<root>/{norm_root}/`)**：\n"
        f"  - `{norm_root}/` 子目錄目前已啟用（`repo_sync.enable: true`），由 `yscb gdrive` 三方狀態機與 Shortcut 分支機制自動納管。詳細操作規範請參閱 `{norm_root}/README.md`。\n"
        f"{ROOT_README_END_MARKER}"
    )


def merge_root_readme_block(
    existing_text: str,
    managed_block: Optional[str] = None,
    *,
    managed_body: str = "",
    repo_sync_root: str = DEFAULT_REPO_SYNC_ROOT,
) -> str:
    """
    Soft-merge the YSCB managed repo_sync block into top-level README.md content.
    Preserves all user-authored text outside the BEGIN/END markers.
    """
    block = (
        managed_block
        or managed_body
        or build_root_readme_managed_block(repo_sync_root=repo_sync_root)
    ).strip()
    if not existing_text or not existing_text.strip():
        return block + "\n"

    begin_idx = existing_text.find(ROOT_README_BEGIN_MARKER)
    end_idx = existing_text.find(ROOT_README_END_MARKER)
    if begin_idx != -1 and end_idx != -1 and end_idx >= begin_idx:
        end_pos = end_idx + len(ROOT_README_END_MARKER)
        before = existing_text[:begin_idx].rstrip()
        after = existing_text[end_pos:].lstrip()
        parts = [p for p in (before, block, after) if p]
        return "\n\n".join(parts) + "\n"

    cleaned = existing_text.rstrip()
    return f"{cleaned}\n\n{block}\n"


def strip_root_readme_block(existing_text: str) -> str:
    """
    Soft-remove the YSCB managed repo_sync block from top-level README.md content.
    Returns the remaining user-authored text (empty string if nothing remains).
    """
    if not existing_text:
        return ""
    begin_idx = existing_text.find(ROOT_README_BEGIN_MARKER)
    end_idx = existing_text.find(ROOT_README_END_MARKER)
    if begin_idx == -1 or end_idx == -1 or end_idx < begin_idx:
        return existing_text

    end_pos = end_idx + len(ROOT_README_END_MARKER)
    before = existing_text[:begin_idx].rstrip()
    after = existing_text[end_pos:].lstrip()
    if before and after:
        return f"{before}\n\n{after}\n"
    if before:
        return f"{before}\n"
    if after:
        return f"{after}\n"
    return ""


def reconcile_root_readme_state(
    config: GDriveConfig,
    transport: AbstractSyncTransport,
    readme_state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Check local cache for the last known 'repo_sync.enable' and 'repo_sync_root' state for this target root.
    Only when a state transition is detected (or first initialization with enable=True)
    does it inspect/update the cloud root README.md.
    """
    state_file = (
        Path(readme_state_path).resolve()
        if readme_state_path is not None
        else Path(uri.resolve("storage.local://gdrive-support/readme_sync_state.json")).resolve()
    )
    target_key = (config.sandbox_dir or config.root_folder_id or "default").strip()
    if not target_key:
        return {"changed": False, "action": "skipped_unconfigured"}

    cache_data: Dict[str, Any] = {"states": {}}
    if state_file.is_file():
        try:
            loaded = vfs.read_json(state_file)
            if isinstance(loaded, dict) and isinstance(loaded.get("states"), dict):
                cache_data = loaded
        except (OSError, ValueError):
            cache_data = {"states": {}}

    states_map: Dict[str, Any] = cache_data.setdefault("states", {})
    curr_enabled = bool(config.repo_sync_enabled)
    curr_root = (
        normalize_remote_rel_path(config.repo_sync_root or DEFAULT_REPO_SYNC_ROOT)
        or DEFAULT_REPO_SYNC_ROOT
    )
    prev_enabled, prev_root = _extract_cached_readme_state(states_map.get(target_key))

    if prev_enabled is not None and prev_enabled == curr_enabled:
        if not curr_enabled or prev_root == curr_root:
            return {"changed": False, "action": "noop_cached", "enabled": curr_enabled}

    if prev_enabled is None and not curr_enabled:
        states_map[target_key] = {"enable": False, "repo_sync_root": curr_root}
        state_file.parent.mkdir(parents=True, exist_ok=True)
        vfs.write_json(state_file, cache_data, indent=2, encoding="utf-8", atomic=True)
        return {"changed": False, "action": "initialized_disabled_cache", "enabled": False}

    action_taken = "none"
    existing_entry = transport.get_entry(REPO_README_FILENAME)

    with tempfile.TemporaryDirectory(prefix="yscb_root_readme_") as tmp_d:
        tmp_path = Path(tmp_d) / REPO_README_FILENAME
        existing_text = ""
        if existing_entry is not None and not existing_entry.is_dir:
            transport.download_file(REPO_README_FILENAME, tmp_path)
            existing_text = tmp_path.read_text(encoding="utf-8")

        if curr_enabled:
            merged_text = merge_root_readme_block(
                existing_text, repo_sync_root=curr_root
            )
            tmp_path.write_text(merged_text, encoding="utf-8")
            in_place_id = (
                existing_entry.file_id
                if existing_entry is not None and not existing_entry.is_dir
                else None
            )
            transport.upload_file(
                tmp_path, REPO_README_FILENAME, in_place_file_id=in_place_id
            )
            action_taken = "soft_merged" if existing_text.strip() else "created"
        else:
            if existing_entry is not None and not existing_entry.is_dir:
                stripped = strip_root_readme_block(existing_text)
                if not stripped.strip():
                    transport.trash_file(REPO_README_FILENAME)
                    action_taken = "removed_to_trash"
                elif stripped != existing_text:
                    tmp_path.write_text(stripped, encoding="utf-8")
                    transport.upload_file(
                        tmp_path,
                        REPO_README_FILENAME,
                        in_place_file_id=existing_entry.file_id,
                    )
                    action_taken = "soft_removed"
                else:
                    action_taken = "unmanaged_preserved"
            else:
                action_taken = "absent_noop"

    states_map[target_key] = {"enable": curr_enabled, "repo_sync_root": curr_root}
    state_file.parent.mkdir(parents=True, exist_ok=True)
    vfs.write_json(state_file, cache_data, indent=2, encoding="utf-8", atomic=True)
    return {"changed": True, "action": action_taken, "enabled": curr_enabled}
