"""Public SDK entrypoint re-exporting core contracts, declarative DSL, and YscbClient."""

from core.execution.event import EventMetadata
from core.execution.runtime import (
    ConcurrencyMode,
    DispatchMode,
    SecurityTier,
    TaskContext,
    TaskOutcome,
    YscbModule,
)
from core.foundation import CancellationToken, HostPath, ProgressEvent
from core.surface.sdk.client import YscbClient
from core.surface.sdk.declarative import (
    Arg,
    Empty,
    ExitCodeProvider,
    HumanRenderable,
    InMemoryModule,
    Module,
    ModuleEnv,
    Option,
    TaskGroup,
    define_event,
    format_output,
    on_event,
    periodic,
    task,
)

__all__: tuple[str, ...] = (
    "Arg",
    "CancellationToken",
    "ConcurrencyMode",
    "DispatchMode",
    "Empty",
    "EventMetadata",
    "ExitCodeProvider",
    "HostPath",
    "HumanRenderable",
    "InMemoryModule",
    "Module",
    "ModuleEnv",
    "Option",
    "ProgressEvent",
    "SecurityTier",
    "TaskContext",
    "TaskGroup",
    "TaskOutcome",
    "YscbClient",
    "YscbModule",
    "define_event",
    "format_output",
    "on_event",
    "periodic",
    "task",
)
