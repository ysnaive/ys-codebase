"""
Core Commands - Contributes Commands Schema Parser & Registry.
100% Python Standard Library.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ArgSpec:
    """規格定義：參數規格 (指令位置參數或選項參數)。"""
    name: str
    description: str = ""
    required: bool = True
    choice: Optional[List[str]] = None


@dataclass
class OptionSpec:
    """規格定義：單一命令選項。"""
    canonical_name: str
    description: str = ""
    alias: List[str] = field(default_factory=list)
    args: Dict[str, ArgSpec] = field(default_factory=dict)
    group_name: str = "default"

    @property
    def takes_value(self) -> bool:
        return bool(self.args)


@dataclass
class CommandSpec:
    """規格定義：單一子命令。"""
    name: str
    description: str = ""
    tier: str = "safe"
    server_compatible: bool = False
    args: Dict[str, ArgSpec] = field(default_factory=dict)
    options: Dict[str, OptionSpec] = field(default_factory=dict)         # 規範名及別名均索引至對應 OptionSpec
    canonical_options: Dict[str, OptionSpec] = field(default_factory=dict) # 僅以規範名索引
    groups: Dict[str, List[str]] = field(default_factory=dict)           # group_name -> list of canonical names
    usage_pros: List[str] = field(default_factory=list)
    usage_cons: List[str] = field(default_factory=list)
    cmd: Dict[str, "CommandSpec"] = field(default_factory=dict)          # FR-12: 遞迴同構子指令樹


@dataclass
class ModuleSpec:
    """規格定義：單一模組及其 CLI 指令清單。"""
    module_name: str
    description: str = ""
    module_alias: List[str] = field(default_factory=list)
    commands: Dict[str, CommandSpec] = field(default_factory=dict)


class CommandsRegistry:
    """
    Commands Contributes 註冊中心。
    負責解析 Contributes Commands Schema、維護別名索引、檢查衝突 (EC-06)。
    """

    def __init__(self) -> None:
        self._modules: Dict[str, ModuleSpec] = {}
        self._alias_to_module: Dict[str, str] = {}

    @staticmethod
    def _parse_args_dict(args_raw: Any) -> Dict[str, ArgSpec]:
        """解析 args 字典結構 ({name: {description, required, choice}}) 為 Dict[str, ArgSpec]。"""
        res: Dict[str, ArgSpec] = {}
        if isinstance(args_raw, dict):
            for arg_name, arg_data in args_raw.items():
                if isinstance(arg_data, dict):
                    choice_val = arg_data.get("choice")
                    if isinstance(choice_val, list):
                        choice_list = [str(c) for c in choice_val]
                    elif choice_val:
                        choice_list = [str(choice_val)]
                    else:
                        choice_list = None
                    res[arg_name] = ArgSpec(
                        name=arg_name,
                        description=str(arg_data.get("description", "")),
                        required=bool(arg_data.get("required", True)),
                        choice=choice_list,
                    )
                else:
                    res[arg_name] = ArgSpec(name=arg_name)
        elif isinstance(args_raw, list):
            for item in args_raw:
                if isinstance(item, dict) and "name" in item:
                    aname = item["name"]
                    choice_val = item.get("choice")
                    choice_list = [str(c) for c in choice_val] if isinstance(choice_val, list) else None
                    res[aname] = ArgSpec(
                        name=aname,
                        description=str(item.get("description", "")),
                        required=bool(item.get("required", True)),
                        choice=choice_list,
                    )
                elif isinstance(item, str):
                    res[item] = ArgSpec(name=item)
        return res

    def register_module(self, module_name: str, commands_data: Dict[str, Any]) -> ModuleSpec:
        """
        解析 commands contributes 結構並註冊模組。
        支援新版 Schema (含 module_alias, cmd, orthogonal groups, args, usage: {pros, cons})。
        """
        if not isinstance(commands_data, dict):
            commands_data = {}

        module_aliases = commands_data.get("module_alias", [])
        if isinstance(module_aliases, str):
            module_aliases = [module_aliases]
        module_aliases = [str(a).strip() for a in module_aliases if str(a).strip()]

        # EC-06: 檢查模組別名衝突
        for alias in module_aliases:
            existing_mod = self._alias_to_module.get(alias)
            if existing_mod is not None and existing_mod != module_name:
                raise ValueError(
                    f"Module alias conflict (EC-06): Alias '{alias}' declared by '{module_name}' "
                    f"conflicts with already registered module '{existing_mod}'."
                )

        for alias in module_aliases:
            self._alias_to_module[alias] = module_name

        mod_desc = commands_data.get("description", "")
        mod_spec = ModuleSpec(
            module_name=module_name,
            description=mod_desc,
            module_alias=module_aliases,
        )

        # 解析 cmd 集合 (判斷是否為新版嵌套結構或舊版扁平結構)
        raw_cmd_map = commands_data.get("cmd")
        if not isinstance(raw_cmd_map, dict):
            raw_cmd_map = {
                k: v for k, v in commands_data.items()
                if k not in ("module_alias", "description") and isinstance(v, dict)
            }

        for cmd_name, raw_spec in raw_cmd_map.items():
            if not isinstance(raw_spec, dict):
                continue
            cmd_spec = self._parse_command_spec(cmd_name, raw_spec)
            mod_spec.commands[cmd_name] = cmd_spec

        self._modules[module_name] = mod_spec
        return mod_spec

    def _parse_command_spec(self, cmd_name: str, raw_spec: Dict[str, Any]) -> CommandSpec:
        desc = raw_spec.get("description", "")
        tier = raw_spec.get("tier", "safe")
        # FR-06: server_compatible 為指令層級原生布林宣告
        server_compatible = bool(raw_spec.get("server_compatible", False))
        cmd_args = self._parse_args_dict(raw_spec.get("args"))

        cmd_spec = CommandSpec(
            name=cmd_name,
            description=desc,
            tier=tier,
            server_compatible=server_compatible,
            args=cmd_args,
        )

        # 解析 usage
        usage_data = raw_spec.get("usage", {})
        if isinstance(usage_data, dict):
            pros = usage_data.get("pros", [])
            cons = usage_data.get("cons", [])
            cmd_spec.usage_pros = [str(p) for p in pros] if isinstance(pros, list) else ([str(pros)] if pros else [])
            cmd_spec.usage_cons = [str(c) for c in cons] if isinstance(cons, list) else ([str(cons)] if cons else [])
        else:
            pros = raw_spec.get("case_pros", [])
            cons = raw_spec.get("case_cons", [])
            cmd_spec.usage_pros = [str(p) for p in pros] if isinstance(pros, list) else ([str(pros)] if pros else [])
            cmd_spec.usage_cons = [str(c) for c in cons] if isinstance(cons, list) else ([str(cons)] if cons else [])

        # 解析正交選項群組 options: { <group_name>: { <option_name>: { ... } } }
        raw_options = raw_spec.get("options", {})
        if isinstance(raw_options, dict):
            for group_name, group_items in raw_options.items():
                if not isinstance(group_items, dict):
                    continue
                cmd_spec.groups[group_name] = []
                for opt_name, opt_data in group_items.items():
                    if not isinstance(opt_data, dict):
                        opt_data = {}
                    canonical = opt_name.lstrip("-")
                    opt_desc = opt_data.get("description", "")
                    aliases = opt_data.get("alias", [])
                    if isinstance(aliases, str):
                        aliases = [aliases]
                    clean_aliases = [a.lstrip("-") for a in aliases if a]
                    opt_args = self._parse_args_dict(opt_data.get("args"))

                    option_spec = OptionSpec(
                        canonical_name=canonical,
                        description=opt_desc,
                        alias=clean_aliases,
                        args=opt_args,
                        group_name=group_name,
                    )
                    cmd_spec.canonical_options[canonical] = option_spec
                    cmd_spec.options[canonical] = option_spec
                    for a in clean_aliases:
                        cmd_spec.options[a] = option_spec
                    cmd_spec.groups[group_name].append(canonical)

        # FR-12: 遞迴解析子指令樹 (cmd: { <sub_name>: { ... } })
        raw_sub_cmd = raw_spec.get("cmd", {})
        if isinstance(raw_sub_cmd, dict):
            for sub_name, sub_spec in raw_sub_cmd.items():
                if isinstance(sub_spec, dict):
                    cmd_spec.cmd[sub_name] = self._parse_command_spec(sub_name, sub_spec)

        return cmd_spec

    def resolve_module_name(self, candidate: str) -> Optional[str]:
        """依據輸入候選字串檢索對應的模組規範名 (優先比對模組名，再比對別名)。"""
        if candidate in self._modules:
            return candidate
        return self._alias_to_module.get(candidate)

    def get_module(self, module_name: str) -> Optional[ModuleSpec]:
        """取得特定模組之 ModuleSpec。"""
        canonical = self.resolve_module_name(module_name)
        return self._modules.get(canonical) if canonical else None

    def get_command(self, module_name: str, cmd_name: str) -> Optional[CommandSpec]:
        """取得特定模組之特定命令 CommandSpec (支援階層名如 'uri list' 或 'uri_list')。"""
        mod = self.get_module(module_name)
        if mod is None:
            return None
        if cmd_name in mod.commands:
            return mod.commands[cmd_name]
        # 嘗試以空格或底線切分路徑走訪
        parts = cmd_name.split() if " " in cmd_name else cmd_name.split("_")
        curr = mod.commands.get(parts[0])
        for p in parts[1:]:
            if curr and curr.cmd and p in curr.cmd:
                curr = curr.cmd[p]
            else:
                return None
        return curr

    def resolve_command_path(
        self, module_name: str, tokens: List[str]
    ) -> Tuple[List[str], Optional[CommandSpec], List[str]]:
        """
        沿 tokens 走訪指令樹，返回 (cmd_path, target_spec, remaining_tokens)。
        例如：tokens = ["uri", "resolve", "project://AGENTS.md"]
        -> cmd_path = ["uri", "resolve"], target_spec = CommandSpec(name="resolve"), remaining_tokens = ["project://AGENTS.md"]
        """
        mod = self.get_module(module_name)
        if mod is None or not tokens:
            return [], None, tokens

        first_token = tokens[0]
        if first_token not in mod.commands:
            return [], None, tokens

        current_spec = mod.commands[first_token]
        cmd_path = [first_token]
        idx = 1

        while idx < len(tokens):
            next_token = tokens[idx]
            if next_token.startswith("-"):
                break
            if current_spec.cmd and next_token in current_spec.cmd:
                current_spec = current_spec.cmd[next_token]
                cmd_path.append(next_token)
                idx += 1
            else:
                break

        return cmd_path, current_spec, tokens[idx:]

    def list_modules(self) -> List[str]:
        """列出所有已註冊的模組名稱。"""
        return sorted(list(self._modules.keys()))

    def all_modules(self) -> Dict[str, ModuleSpec]:
        """取得所有已註冊模組的字典。"""
        return self._modules
