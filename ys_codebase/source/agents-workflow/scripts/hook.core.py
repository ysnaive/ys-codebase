"""
Microkernel Lifecycle Hook for agents-workflow.
Listens to 'on_reload' event to autonomously execute release transaction for all active targets.
"""
import sys
from typing import Any

from agents_workflow.publisher import ReleasePublisher
from core.log import log


def _log_hook(*args: Any, **kwargs: Any) -> None:
    file_arg = kwargs.get("file")
    stream = "stderr" if file_arg is sys.stderr else "stdout"
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    text = sep.join(str(a) for a in args)
    log(text, stream=stream, end=end)


def on_reload(ctx=None) -> None:
    """
    Autonomously triggered on microkernel Stage 4 reload.
    Executes full 4-step atomic release transaction for all active targets.
    """
    try:
        publisher = ReleasePublisher()
        res = publisher.release_all(force=False)
        if res.get("success", False):
            if res.get("short_circuited", False):
                _log_hook(f"[agents-workflow:hook] Auto-release skipped on reload (no changes detected, {res.get('skipped_count', 0)} files up to date).")
            else:
                _log_hook(f"[agents-workflow:hook] Auto-released on reload ({res.get('written_count', 0)} written, {res.get('skipped_count', 0)} unchanged, {res.get('removed_count', 0)} removed, targets: {', '.join(res.get('active_targets', []))}).")
        else:
            _log_hook(f"[agents-workflow:hook] Auto-release failed on reload: {res.get('error', 'Unknown')}", file=sys.stderr)
    except Exception as e:
        _log_hook(f"[agents-workflow:hook] Auto-release on reload failed: {e}", file=sys.stderr)


def on_pre_cli_dispatch(ctx=None) -> bool:
    """
    在 CLI 命令分發前觸發，呼叫 ensure_jit_release()。
    若來源特徵指紋變更，原地執行 release_all(force=False) 自癒物化至 Targets；
    若無變更 (Clean)，<1ms 極速短路跳過。

    :return: 是否發生實質物化寫入
    """
    try:
        from agents_workflow.publisher import ensure_jit_release
        return ensure_jit_release()
    except Exception as e:
        _log_hook(f"[agents-workflow:hook] Warning: Failed during on_pre_cli_dispatch: {e}", file=sys.stderr)
        return False


def on_register_file_spaces(ctx=None) -> bool:
    """當 SpaceRegistry 重載時，依當前活躍 release_target 投影路徑動態註冊 agents-workflow/gitignore 空間。"""
    try:
        registry = ctx.get("registry") if isinstance(ctx, dict) else getattr(ctx, "registry", None)
        if registry is None:
            return False
        register_fn = getattr(registry, "register_space", None) or getattr(
            registry, "define_ephemeral_space", None
        )
        if not callable(register_fn):
            return False

        proj_root_obj = getattr(registry, "project_root", None)
        proj_root = str(proj_root_obj) if proj_root_obj is not None else None
        publisher = ReleasePublisher()
        rel_paths = publisher.collect_gitignore_patterns(proj_root=proj_root)
        register_fn(
            "agents-workflow/gitignore",
            {
                "description": "agents-workflow 活躍發布目標物化檔案與私有目錄忽略規則",
                "entries": ["project://"],
                "include": rel_paths,
                "watch": False,
            },
        )
        return True
    except Exception as e:
        _log_hook(f"[agents-workflow:hook] Warning: Failed during on_register_file_spaces: {e}", file=sys.stderr)
        return False


