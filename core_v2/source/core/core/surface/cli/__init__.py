"""Domain 6.2: Zero-import static CLI router, 5-layer CallerMode, 4x3 security gate, and 1.x HelpRenderer."""

from core.surface.cli.approval import (
    ApprovalTokenStore,
    PendingApprovalRecord,
    SecurityGateResult,
    compute_approval_args_hash,
    evaluate_security_gate,
)
from core.surface.cli.caller_mode import (
    CallerEnvironment,
    CallerMode,
    CliInputStream,
    CliOutputStream,
    detect_caller_environment,
    detect_caller_mode,
)
from core.surface.cli.entrypoint import (
    CLI_DEFAULT_PROVIDER_URL,
    CLI_DEFAULT_SELF_UPDATE_URL,
    CliKernelFactoryFn,
    CliKernelSession,
    main,
    register_cli_kernel_factory,
)
from core.surface.cli.help_renderer import HelpRenderer, render_task_help
from core.surface.cli.index import (
    TASKS_INDEX_SCHEMA_VERSION,
    CliArgSpec,
    CliOptionSpec,
    CliSubscriptionSpec,
    IndexedTaskEntry,
    ModuleTasksIndex,
    WorkspaceTasksIndexCache,
    compile_tasks_index,
)
from core.surface.cli.parser import (
    CliCommandNode,
    CliRouteKind,
    CliRouteResolution,
    GlobalCliFlags,
    build_cli_command_tree,
    extract_global_flags,
    resolve_cli_invocation,
)

__all__: tuple[str, ...] = (
    "ApprovalTokenStore",
    "CLI_DEFAULT_PROVIDER_URL",
    "CLI_DEFAULT_SELF_UPDATE_URL",
    "CallerEnvironment",
    "CallerMode",
    "CliArgSpec",
    "CliCommandNode",
    "CliInputStream",
    "CliKernelFactoryFn",
    "CliKernelSession",
    "CliOptionSpec",
    "CliOutputStream",
    "CliRouteKind",
    "CliRouteResolution",
    "CliSubscriptionSpec",
    "GlobalCliFlags",
    "HelpRenderer",
    "IndexedTaskEntry",
    "ModuleTasksIndex",
    "PendingApprovalRecord",
    "SecurityGateResult",
    "TASKS_INDEX_SCHEMA_VERSION",
    "WorkspaceTasksIndexCache",
    "build_cli_command_tree",
    "compile_tasks_index",
    "compute_approval_args_hash",
    "detect_caller_environment",
    "detect_caller_mode",
    "evaluate_security_gate",
    "extract_global_flags",
    "main",
    "register_cli_kernel_factory",
    "render_task_help",
    "resolve_cli_invocation",
)
