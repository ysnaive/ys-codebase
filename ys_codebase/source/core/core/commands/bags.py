"""
Core Commands - Structured Command Bag Dataclasses.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CmdOption:
    """
    Structured Command Option representation.
    """
    name: str          # Canonical option name (without leading dashes)
    params: Any = True # Value associated with option (True for flags, value for parameterized options)


@dataclass(frozen=True)
class CmdBags:
    """
    Structured and immutable Command Context Bag passed to command handlers.
    """
    raw_cmd: str = ""                                  # Full raw command line / arguments string
    command: str = ""                                  # Target command name
    args: List[str] = field(default_factory=list)     # Positional arguments
    options: Dict[str, CmdOption] = field(default_factory=dict) # Options indexed by canonical name

    def has_option(self, name: str) -> bool:
        """Check if option is present."""
        return name in self.options

    def get_option(self, name: str) -> Optional[CmdOption]:
        """Get option by canonical name."""
        return self.options.get(name)

    def get_option_value(self, name: str, default: Any = None) -> Any:
        """Get option parameter value or default."""
        opt = self.options.get(name)
        return opt.params if opt is not None else default
