"""
Core Commands - Option Resolver & Orthogonal Group Validation.
100% Python Standard Library.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from core.commands.bags import CmdOption
from core.commands.registry import CommandSpec, OptionSpec

_NEGATIVE_NUMBER_RE = re.compile(r"^-\d+(?:\.\d+)?$")


class OptionResolutionError(Exception):
    """參數解析異常基類。"""
    pass


class MutualExclusionError(OptionResolutionError):
    """同正交群組多選互斥衝突異常。"""
    pass


class MissingValueError(OptionResolutionError):
    """帶參 Option 缺少參數值異常。"""
    pass


class InvalidChoiceError(OptionResolutionError):
    """參數或選項值不符合 choice 列舉約束異常。"""
    pass


class MissingArgumentError(OptionResolutionError):
    """缺少必填位置參數異常。"""
    pass


class OptionResolver:
    """
    參數解析器。
    負責正交群組互斥檢查、Option 別名轉規範名、args 與 choice 驗證及參數切分。
    """

    @classmethod
    def _is_negative_number_token(cls, token: str, cmd_spec: Optional[CommandSpec]) -> bool:
        """判斷 token 是否為負數純量（且未被註冊為顯式選項名稱）。"""
        if not isinstance(token, str) or not _NEGATIVE_NUMBER_RE.match(token):
            return False
        if cmd_spec is not None and token.lstrip("-") in cmd_spec.options:
            return False
        return True

    @staticmethod
    def _store_resolved_option(
        resolved_options: Dict[str, CmdOption],
        canonical: str,
        val: Any,
    ) -> None:
        """寫入已解析之選項，若為重複出現的 dep 選項則以分號串接。"""
        if (
            canonical == "dep"
            and "dep" in resolved_options
            and isinstance(resolved_options["dep"].params, str)
            and isinstance(val, str)
        ):
            val = f"{resolved_options['dep'].params};{val}"
        resolved_options[canonical] = CmdOption(name=canonical, params=val)

    @classmethod
    def resolve(
        cls,
        cmd_spec: Optional[CommandSpec],
        raw_args: List[str],
    ) -> Tuple[List[str], Dict[str, CmdOption]]:
        """
        將 CLI 原始參數陣列解析為 (positional_args, options)，並執行必填與 choice 校驗。
        """
        positional_args: List[str] = []
        resolved_options: Dict[str, CmdOption] = {}
        seen_groups: Dict[str, str] = {}  # group_name -> canonical_name of option used

        idx = 0
        while idx < len(raw_args):
            token = raw_args[idx]

            # 遇到獨立的 "--" 視為選項結束標誌，其後皆為位置參數
            if token == "--":
                positional_args.extend(raw_args[idx + 1:])
                break

            # 選項標記 (- 開頭，非單一連字號，且非負數純量)
            if len(token) > 1 and token.startswith("-") and not cls._is_negative_number_token(token, cmd_spec):
                # 切分 --key=val 形式
                if "=" in token:
                    raw_key, raw_val = token.split("=", 1)
                    has_inline_val = True
                else:
                    raw_key = token
                    raw_val = None
                    has_inline_val = False

                clean_key = raw_key.lstrip("-")
                opt_spec: Optional[OptionSpec] = None

                if cmd_spec is not None:
                    opt_spec = cmd_spec.options.get(clean_key)

                if opt_spec is not None:
                    canonical = opt_spec.canonical_name
                    grp = opt_spec.group_name

                    # 正交群組互斥約束檢查
                    if grp and grp != "default":
                        if grp in seen_groups and seen_groups[grp] != canonical:
                            prev_canonical = seen_groups[grp]
                            raise MutualExclusionError(
                                f"Mutual exclusion conflict (EC-02): Option '{token}' conflicts with "
                                f"'--{prev_canonical}'. Both belong to orthogonal group '{grp}' and cannot be used together."
                            )
                        seen_groups[grp] = canonical

                    # 帶參 Option 檢查
                    if opt_spec.takes_value:
                        if has_inline_val and raw_val is not None:
                            val: Any = raw_val
                        else:
                            # 需要消耗下一個參數
                            if idx + 1 < len(raw_args) and (
                                not raw_args[idx + 1].startswith("-")
                                or raw_args[idx + 1] == "-"
                                or cls._is_negative_number_token(raw_args[idx + 1], cmd_spec)
                            ):
                                idx += 1
                                val = raw_args[idx]
                            else:
                                first_arg_name = next(iter(opt_spec.args.keys())) if opt_spec.args else "value"
                                raise MissingValueError(
                                    f"Missing option value (EC-03): Option '{token}' requires a value "
                                    f"(e.g. '{token}=<{first_arg_name}>' or '{token} <{first_arg_name}>')."
                                )

                        # 選項 choice 約束檢查
                        if opt_spec.args:
                            first_arg = next(iter(opt_spec.args.values()))
                            if first_arg.choice and str(val) not in first_arg.choice:
                                allowed_str = " | ".join(first_arg.choice)
                                raise InvalidChoiceError(
                                    f"Invalid value '{val}' for option '{token}' (EC-07). "
                                    f"Allowed choices: [{allowed_str}]."
                                )
                    else:
                        # 布林旗標 Flag
                        if has_inline_val and raw_val is not None:
                            val = raw_val.lower() not in ("false", "0", "no")
                        else:
                            val = True

                    cls._store_resolved_option(resolved_options, canonical, val)

                else:
                    # 未在 spec 定義之通用或未遷移選項
                    canonical = clean_key
                    if has_inline_val and raw_val is not None:
                        val = raw_val
                    else:
                        val = True
                    cls._store_resolved_option(resolved_options, canonical, val)

            else:
                positional_args.append(token)

            idx += 1

        # 位置參數必填性與 choice 檢查
        if cmd_spec and cmd_spec.args:
            cmd_args_list = list(cmd_spec.args.values())
            for i, arg_spec in enumerate(cmd_args_list):
                if i < len(positional_args):
                    actual_val = positional_args[i]
                    if arg_spec.choice and actual_val not in arg_spec.choice:
                        allowed_str = " | ".join(arg_spec.choice)
                        raise InvalidChoiceError(
                            f"Invalid value '{actual_val}' for argument '{arg_spec.name}' (EC-07). "
                            f"Allowed choices: [{allowed_str}]."
                        )
                else:
                    if arg_spec.required:
                        raise MissingArgumentError(
                            f"Missing required argument '{arg_spec.name}' (EC-08)."
                        )

        return positional_args, resolved_options
