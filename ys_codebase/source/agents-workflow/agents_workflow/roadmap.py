"""Roadmap 與 TODO 雙層儲備與立項遷入管理器 (RoadmapManager & TodoManager)

負責 `workflow.roadmap://` (`plans/roadmap/`) 下之：
- Tier 1 (`TODO.md`)：輕量待辦單行免讀盲寫追加 (`todo add`)、單調遞增編號、過濾檢索 (`todo list`) 與單/多筆原子剪切立項 (`todo promote`)。
- Tier 2 (`{topic}.md`)：長期技術路線圖掃描 (`roadmap list`)、狀態過濾與物理搬移立項 (`roadmap promote`)。
"""

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple


def _resolve_workflow_dir(uri_scheme: str, fallback_rel: str, host_dir: Optional[str] = None) -> Path:
    """解析 workflow.*:// 語意 URI，若未定義則安全回退至專案相對路徑。"""
    try:
        from core import uri  # type: ignore
        resolved_uri = uri.resolve(uri_scheme)
        if resolved_uri and not str(resolved_uri).startswith("!"):
            return Path(resolved_uri).resolve()
    except Exception:
        pass

    base = Path(host_dir).resolve() if host_dir else Path.cwd().resolve()
    return (base / fallback_rel).resolve()


@dataclass
class RoadmapItem:
    """Roadmap 條目結構化模型 (Tier 2)"""
    topic: str                     # 主題名稱
    filename: str                  # 實體檔案名稱
    path: Path                     # 絕對路徑
    title: str                     # 頂部 H1 標題
    status: str                    # 狀態 (Backlog | Proposed | Ready | Deferred)
    date: str                      # 歸檔/更新日期 (YYYY-MM-DD)
    problem_summary: str           # 問題背景摘要
    has_valid_header: bool         # 是否具備合規之標準元資料 Header
    scope: str = ""                # 目標範疇 (> 目標範疇：)
    trigger: str = ""              # 前置解鎖條件 (> 前置解鎖條件：)


@dataclass
class TodoItem:
    """TODO.md 單筆輕量待辦結構化模型 (Tier 1)"""
    todo_id: str                   # 標準化編號 (如 'TODO-01')
    number: int                    # 整數編號 (如 1)
    title: str                     # 待辦動作標題
    date: str                      # 建立日期 (YYYY-MM-DD)
    scope: str                     # 目標範疇
    note: str                      # 備忘與解法要點
    raw_block: str                 # 完整 Markdown 區塊文本


class RoadmapManager:
    """Roadmap 策略資產掃描、過濾與立項物理遷入管理器 (零外部依賴)"""

    def __init__(
        self,
        roadmap_dir: Optional[Path] = None,
        plans_dir: Optional[Path] = None,
        host_dir: Optional[str] = None,
    ):
        if roadmap_dir is not None:
            self.roadmap_dir = Path(roadmap_dir).resolve()
        else:
            resolved = None
            try:
                from core import uri  # type: ignore
                resolved_uri = uri.resolve("workflow.roadmap://")
                if resolved_uri and not str(resolved_uri).startswith("!"):
                    resolved = Path(resolved_uri).resolve()
            except Exception:
                pass

            if resolved is None:
                base = Path(host_dir).resolve() if host_dir else Path.cwd().resolve()
                if (base / "plans" / "roadmap").exists():
                    self.roadmap_dir = (base / "plans" / "roadmap").resolve()
                elif (base / "roadmap").exists():
                    self.roadmap_dir = (base / "roadmap").resolve()
                else:
                    self.roadmap_dir = (base / "plans" / "roadmap").resolve()
            else:
                self.roadmap_dir = resolved

        if plans_dir is not None:
            self.plans_dir = Path(plans_dir).resolve()
        else:
            self.plans_dir = _resolve_workflow_dir("workflow.plans://", "plans", host_dir=host_dir)

    def scan_roadmaps(self, status_filter: Optional[str] = None) -> List[RoadmapItem]:
        """
        掃描 roadmap_dir 下的所有 *.md 策略路線圖檔案（自動排除集中式帳本 TODO.md）。
        支援選填之 status_filter（不區分大小寫）過濾，並依日期倒序排列。
        """
        if not self.roadmap_dir.exists() or not self.roadmap_dir.is_dir():
            return []

        norm_filter = status_filter.strip().lower() if status_filter and status_filter.strip() else None

        items: List[RoadmapItem] = []
        for file_path in sorted(self.roadmap_dir.glob("*.md"), key=lambda p: p.name):
            if not file_path.is_file():
                continue
            # EC-06: 自動排除 Tier 1 集中式待辦帳本 TODO.md
            if file_path.name.lower() == "todo.md":
                continue
            item = self._parse_roadmap_file(file_path)
            if item:
                if norm_filter and item.status.strip().lower() != norm_filter:
                    continue
                items.append(item)

        items.sort(key=lambda x: (x.date if x.date else "", x.filename), reverse=True)
        return items

    def _parse_roadmap_file(self, file_path: Path) -> Optional[RoadmapItem]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return None

        filename = file_path.name
        stem = file_path.stem
        lines = content.splitlines()

        title = stem
        topic = stem
        status = "Backlog"
        date = ""
        scope = ""
        trigger = ""
        has_valid_header = False

        # 提取 H1 標題
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                break

        # 提取 Header 區塊引用 (> 主題：..., > 狀態：..., > 歸檔日期：..., > 目標範疇：..., > 前置解鎖條件：...)
        for line in lines[:35]:
            trimmed = line.strip()
            if trimmed.startswith(">"):
                val = trimmed.lstrip(">").strip()
                if "主題" in val or "Topic" in val:
                    m = re.search(r"[:：]\s*(.+)", val)
                    if m:
                        topic = m.group(1).strip()
                        has_valid_header = True
                elif "狀態" in val or "Status" in val:
                    m = re.search(r"[:：]\s*(.+)", val)
                    if m:
                        status = m.group(1).strip()
                        has_valid_header = True
                elif "日期" in val or "Date" in val:
                    m = re.search(r"[:：]\s*(.+)", val)
                    if m:
                        date = m.group(1).strip()
                        has_valid_header = True
                elif "目標範疇" in val or "Scope" in val:
                    m = re.search(r"[:：]\s*(.+)", val)
                    if m:
                        scope = m.group(1).strip()
                elif "前置解鎖條件" in val or "Trigger" in val:
                    m = re.search(r"[:：]\s*(.+)", val)
                    if m:
                        trigger = m.group(1).strip()

        # 提取 "## 1. 背景與長期願景" 或舊版 "## 1. 問題陳述" 摘要
        summary_lines = []
        in_problem_section = False
        for line in lines:
            if re.match(r"^##\s+1\.\s+.*(問題|背景|陳述|願景|動機|目標|定位|Problem|Background|Vision|Intent|Motivation)", line):
                in_problem_section = True
                continue
            if in_problem_section:
                if line.startswith("## "):
                    break
                stripped = line.strip()
                if stripped and not stripped.startswith("###") and not stripped.startswith("```"):
                    summary_lines.append(stripped)
                    if len(summary_lines) >= 3:
                        break

        if summary_lines:
            problem_summary = " ".join(summary_lines)
            if len(problem_summary) > 200:
                problem_summary = problem_summary[:197] + "..."
        else:
            fallback_lines = []
            for line in lines:
                s = line.strip()
                if s and not s.startswith("#") and not s.startswith(">") and not s.startswith("---"):
                    fallback_lines.append(s)
                    if len(fallback_lines) >= 2:
                        break
            problem_summary = " ".join(fallback_lines) if fallback_lines else "無背景說明摘要"
            if len(problem_summary) > 200:
                problem_summary = problem_summary[:197] + "..."

        return RoadmapItem(
            topic=topic,
            filename=filename,
            path=file_path,
            title=title,
            status=status,
            date=date,
            problem_summary=problem_summary,
            has_valid_header=has_valid_header,
            scope=scope,
            trigger=trigger,
        )

    def format_summary_table(
        self,
        items: Optional[List[RoadmapItem]] = None,
        status_filter: Optional[str] = None,
    ) -> str:
        """格式化輸出極簡 ASCII / Markdown 摘要對照表。"""
        if items is None:
            items = self.scan_roadmaps(status_filter=status_filter)

        if not items:
            filter_note = f" (過濾狀態: {status_filter})" if status_filter else ""
            return (
                f"[agents-workflow:roadmap] 目前無任何待啟動之 Roadmap 技術儲備{filter_note}。\n"
                f"掃描目錄: {self.roadmap_dir}\n"
                f"可透過 /research 調研結案或 /roadmap 新增長期技術路線圖。"
            )

        col_w = 96
        divider = "=" * col_w
        header = f"{'Roadmap 檔名 / 主題':<38} | {'狀態':<10} | {'更新日期':<10} | {'核心背景摘要'}"
        sub_divider = "-" * col_w

        rows = [divider, header, sub_divider]
        for item in items:
            stem = item.path.stem if item.path else item.topic
            if item.topic and item.topic != stem:
                combined_topic = f"{stem} ({item.topic})"
            else:
                combined_topic = stem
            topic_disp = combined_topic if len(combined_topic) <= 36 else combined_topic[:33] + "..."
            status_disp = item.status[:10]
            date_disp = item.date[:10] if item.date else "未標註"
            summary_disp = item.problem_summary if len(item.problem_summary) <= 48 else item.problem_summary[:45] + "..."
            rows.append(f"{topic_disp:<38} | {status_disp:<10} | {date_disp:<10} | {summary_disp}")

        rows.append(divider)
        return "\n".join(rows)

    def get_roadmap(self, topic_or_file: str) -> Optional[RoadmapItem]:
        """依主題名稱或檔名精準查找單一 Roadmap 條目（自動排除 TODO.md）。"""
        if not topic_or_file or topic_or_file.strip().lower() in ("todo", "todo.md"):
            return None
        q = topic_or_file.strip()
        items = self.scan_roadmaps()
        for item in items:
            if (
                item.path.stem == q
                or item.filename == q
                or item.filename == f"{q}.md"
                or item.topic == q
            ):
                return item
        for item in items:
            if q.lower() in item.topic.lower() or q.lower() in item.filename.lower():
                return item
        return None

    def promote_roadmap(
        self,
        topic_or_file: str,
        model: str = "Unknown",
        target_plan: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """
        將指定之長期路線圖物理搬移 (shutil.move) 至新建或既有之計畫目錄下命名為 roadmap.md，
        並以當輪 --model 初始化伴隨 changelog.md (Consume-on-Promote)。
        """
        q = (topic_or_file or "").strip()
        if not q or q.lower() in ("todo", "todo.md"):
            return {
                "success": False,
                "error": (
                    "無法將 'TODO.md' 作為策略路線圖立項。 "
                    "[Fix Hint: 若要將 TODO.md 內的輕量待辦立項，請改用 'todo promote <TODO-ID> --slug <slug>']"
                ),
            }

        items = self.scan_roadmaps()
        exact_matches = [
            it for it in items
            if it.path.stem == q or it.filename == q or it.filename == f"{q}.md" or it.topic == q
        ]
        if len(exact_matches) == 1:
            matched = exact_matches[0]
        else:
            fuzzy_matches = [
                it for it in items
                if q.lower() in it.path.stem.lower() or q.lower() in it.topic.lower()
            ]
            if len(fuzzy_matches) == 1:
                matched = fuzzy_matches[0]
            elif len(fuzzy_matches) > 1:
                cand_names = ", ".join(it.path.stem for it in fuzzy_matches)
                return {
                    "success": False,
                    "error": (
                        f"關鍵字 '{q}' 同時匹配多個路線圖檔案 ({cand_names})。 "
                        f"[Fix Hint: 請傳入精確檔名 stem 以避免歧義]"
                    ),
                }
            else:
                avail = ", ".join(it.path.stem for it in items[:8]) if items else "無可用路線圖"
                return {
                    "success": False,
                    "error": (
                        f"於 '{self.roadmap_dir}' 找不到匹配 '{q}' 之路線圖檔案（目前可用：{avail}）。 "
                        f"[Fix Hint: 請先執行 'roadmap list' 查詢正確主題名稱]"
                    ),
                }

        clean_model = model.strip() if model and isinstance(model, str) and model.strip() else "Unknown"
        if clean_model.startswith("[") and clean_model.endswith("]"):
            clean_model = "Unknown"

        # 解析目標計畫目錄（新建 Seeded 目錄或遷入既有 --plan 目錄）
        if target_plan:
            from .plans.scanner import PlanScanner
            scanner = PlanScanner(plans_dir=self.plans_dir)
            resolved_dir, err = scanner.resolve_target_plan_dir(target_plan)
            if err or resolved_dir is None:
                return {
                    "success": False,
                    "error": f"{err or '找不到指定之目標計畫目錄'} [Fix Hint: 請確認 --plan 指定之目錄已存在於 plans/ 下]",
                }
            target_dir = resolved_dir
            # 若 target_plan 為子計畫目錄 (sub_*)，自動於父計畫之 umbrella_overview.md 補登子計畫名稱，防止 plan verify 產生未登記 WARN
            if target_dir.name.startswith("sub_"):
                umb_md = target_dir.parent / "umbrella_overview.md"
                if umb_md.is_file():
                    try:
                        u_text = umb_md.read_text(encoding="utf-8", errors="replace")
                        if target_dir.name not in u_text:
                            umb_md.write_text(
                                u_text.rstrip() + f"\n- `{target_dir.name}`\n",
                                encoding="utf-8",
                            )
                    except Exception:
                        pass
        else:
            now_prefix = datetime.now().strftime("%Y_%m_%d_%H%M")
            clean_stem = re.sub(r"[^a-z0-9_]+", "_", matched.path.stem.lower()).strip("_")
            if clean_stem.endswith("_roadmap"):
                clean_stem = clean_stem[:-8].strip("_") or clean_stem
            if not clean_stem:
                clean_stem = "roadmap_plan"
            target_dir = (self.plans_dir / f"{now_prefix}_{clean_stem}").resolve()
            target_dir.mkdir(parents=True, exist_ok=True)

        dest_roadmap = target_dir / "roadmap.md"
        is_appended = False
        if dest_roadmap.exists():
            # 若目標目錄已存在 roadmap.md (多路線圖合流子計畫情境)，無損追加合併內容
            existing_text = dest_roadmap.read_text(encoding="utf-8", errors="replace").rstrip()
            incoming_text = matched.path.read_text(encoding="utf-8", errors="replace").strip()
            dest_roadmap.write_text(
                f"{existing_text}\n\n---\n\n# Part 合流路線圖：{matched.title}\n\n> 來源路線圖：{matched.filename}\n\n{incoming_text}\n",
                encoding="utf-8",
            )
            matched.path.unlink()
            is_appended = True
        else:
            shutil.move(str(matched.path), str(dest_roadmap))

        from .plans.verifier import PlanVerifier
        verifier = PlanVerifier(plans_dir=self.plans_dir)
        action_verb = "追加合併至既有" if is_appended else "物理遷入為"
        verifier.append_changelog_entry(
            target_dir,
            summary=f"自長期路線圖 [{matched.filename}] 立項{action_verb} roadmap.md (Consume-on-Promote)",
            log_type="PHASE",
            model=clean_model,
        )

        disp_plan = (
            f"{target_dir.parent.name}/{target_dir.name}"
            if target_dir.name.startswith("sub_") and target_dir.parent != self.plans_dir
            else target_dir.name
        )

        msg = (
            f"[agents-workflow:roadmap] [SUCCESS] 已將路線圖物理遷入計畫目錄：\n"
            f"  * 來源路線圖 : {matched.filename} (已自 {self.roadmap_dir.name}/ 移除)\n"
            f"  * 目標目錄   : {target_dir}\n"
            f"  * 遷入檔案   : {dest_roadmap.name} (+ changelog.md)\n"
            f"  * 當前狀態   : Seeded\n"
            f"  * [!] 下一步指引 : 請直接於該既有目錄 '{disp_plan}' 內原地建立 P00_discuss.md、fast_track_plan.md 或 revision_log.md，嚴禁重複新建第二個時間戳資料夾！"
        )

        return {
            "success": True,
            "plan_dir": target_dir,
            "plan_name": disp_plan,
            "roadmap_path": dest_roadmap,
            "source_path": matched.path,
            "is_appended": is_appended,
            "model": clean_model,
            "message": msg,
        }


class TodoManager:
    """Tier 1 輕量待辦帳本 (plans/roadmap/TODO.md) 免讀盲寫與原子拔除立項管理器"""

    SLUG_PATTERN = re.compile(r"^[a-z0-9_]+$")
    HEADER_LAST_ID_RE = re.compile(r"^>\s*最後分配編號\s*[:：]\s*(\d+)\s*$")
    ITEM_HEADER_RE = re.compile(r"^###\s+\[TODO-(\d+)\]\s+(.+)$", re.IGNORECASE)

    def __init__(
        self,
        roadmap_dir: Optional[Path] = None,
        plans_dir: Optional[Path] = None,
        host_dir: Optional[str] = None,
    ):
        rm = RoadmapManager(roadmap_dir=roadmap_dir, plans_dir=plans_dir, host_dir=host_dir)
        self.roadmap_dir = rm.roadmap_dir
        self.plans_dir = rm.plans_dir

    @property
    def todo_file(self) -> Path:
        return self.roadmap_dir / "TODO.md"

    @staticmethod
    def normalize_todo_num(raw_id: str) -> Optional[int]:
        """將 '1', '01', 'todo-01', 'TODO-01', '[TODO-01]' 正規化為正整數編號。"""
        if not raw_id or not isinstance(raw_id, str):
            return None
        s = raw_id.strip().strip("[]").strip()
        m = re.match(r"^(?:todo[-_]?)?(\d+)$", s, flags=re.IGNORECASE)
        if not m:
            return None
        val = int(m.group(1))
        return val if val > 0 else None

    @classmethod
    def normalize_todo_id(cls, raw_id: str) -> Optional[str]:
        """將 '1', '01', 'todo-1', 'TODO-01', '[TODO-01]' 正規化為標準大寫 'TODO-01'。"""
        num = cls.normalize_todo_num(raw_id)
        return f"TODO-{num:02d}" if num is not None else None

    def _build_initial_todo_ledger(self, today_str: str, model: str) -> str:
        return (
            f"# 專案輕量級待辦與技術債帳本 (TODO Ledger)\n\n"
            f"> 主題：專案輕量級待辦與技術債帳本  \n"
            f"> 更新日期：{today_str}  \n"
            f"> 狀態：Active  \n"
            f"> 最後分配編號：0  \n"
            f"> 模型：{model}  \n\n"
            f"---\n\n"
            f"## 待辦清單 (Active TODOs)\n"
        )

    def _parse_ledger(self, content: str) -> Tuple[List[str], int, List[TodoItem]]:
        """
        解析 TODO.md 內容，回傳 (前言與表頭行清單, Header 記錄之最後分配編號, TodoItem 清單)。
        """
        lines = content.splitlines()
        header_last_id = 0
        for line in lines[:35]:
            m = self.HEADER_LAST_ID_RE.match(line.strip())
            if m:
                header_last_id = int(m.group(1))
                break

        first_item_line_idx = len(lines)
        item_starts: List[Tuple[int, int, str]] = []
        for idx, line in enumerate(lines):
            m = self.ITEM_HEADER_RE.match(line.strip())
            if m:
                if first_item_line_idx == len(lines):
                    first_item_line_idx = idx
                item_starts.append((idx, int(m.group(1)), m.group(2).strip()))

        preamble_lines = lines[:first_item_line_idx]
        while preamble_lines and not preamble_lines[-1].strip():
            preamble_lines.pop()

        items: List[TodoItem] = []
        for i, (start_idx, num, title) in enumerate(item_starts):
            end_idx = item_starts[i + 1][0] if i + 1 < len(item_starts) else len(lines)
            block_lines = lines[start_idx:end_idx]
            while block_lines and not block_lines[-1].strip():
                block_lines.pop()

            date_val = ""
            scope_val = "general"
            note_val = ""
            for bl in block_lines[1:]:
                s = bl.strip()
                if "建立日期" in s:
                    m_d = re.search(r"[:：]\s*(.+)", s)
                    if m_d:
                        date_val = m_d.group(1).strip()
                elif "目標範疇" in s:
                    m_s = re.search(r"[:：]\s*(.+)", s)
                    if m_s:
                        scope_val = m_s.group(1).strip().strip("`")
                elif "備忘與解法要點" in s or "備忘" in s:
                    m_n = re.search(r"[:：]\s*(.+)", s)
                    if m_n:
                        note_val = m_n.group(1).strip()

            todo_id = f"TODO-{num:02d}"
            items.append(
                TodoItem(
                    todo_id=todo_id,
                    number=num,
                    title=title,
                    date=date_val,
                    scope=scope_val,
                    note=note_val,
                    raw_block="\n".join(block_lines),
                )
            )

        return preamble_lines, header_last_id, items

    @staticmethod
    def _update_preamble_headers(
        preamble_lines: List[str],
        today_str: str,
        last_id: int,
        model: Optional[str] = None,
    ) -> List[str]:
        updated: List[str] = []
        found_last_id = False
        found_date = False

        for line in preamble_lines:
            s = line.strip()
            if s.startswith(">") and "更新日期" in s:
                updated.append(f"> 更新日期：{today_str}  ")
                found_date = True
            elif s.startswith(">") and "最後分配編號" in s:
                updated.append(f"> 最後分配編號：{last_id}  ")
                found_last_id = True
            elif model is not None and s.startswith(">") and ("模型" in s or "model" in s.lower()):
                updated.append(f"> 模型：{model}  ")
            else:
                updated.append(line)

        if not found_last_id:
            # 若舊檔缺少 '> 最後分配編號：'，自動插入於 '> 狀態：' 之後
            new_updated: List[str] = []
            inserted = False
            for line in updated:
                new_updated.append(line)
                if not inserted and line.strip().startswith(">") and "狀態" in line:
                    new_updated.append(f"> 最後分配編號：{last_id}  ")
                    inserted = True
            if not inserted:
                new_updated.insert(min(3, len(new_updated)), f"> 最後分配編號：{last_id}  ")
            updated = new_updated

        return updated

    def add_todo(
        self,
        title: str,
        scope: str = "general",
        note: str = "無",
        model: str = "Unknown",
    ) -> TodoItem:
        """
        單行免讀盲寫追加待辦至 plans/roadmap/TODO.md。
        自動維護頂部 '> 最後分配編號：N' 單調遞增計數器，保證絕不發生歷史編號碰撞。
        """
        clean_title = (title or "").strip().replace("\r", " ").replace("\n", " ")
        if not clean_title:
            raise ValueError("待辦標題 (title) 不可為空白。")

        clean_scope = (scope or "general").strip().replace("\r", " ").replace("\n", " ").strip("`") or "general"
        clean_note = (note or "無").strip().replace("\r", " ").replace("\n", " ") or "無"
        clean_model = (model or "Unknown").strip() or "Unknown"
        if clean_model.startswith("[") and clean_model.endswith("]"):
            clean_model = "Unknown"

        today_str = datetime.now().strftime("%Y-%m-%d")

        if not self.todo_file.exists():
            raw_content = self._build_initial_todo_ledger(today_str, clean_model)
        else:
            raw_content = self.todo_file.read_text(encoding="utf-8", errors="replace")

        preamble_lines, header_last_id, existing_items = self._parse_ledger(raw_content)
        max_existing = max((it.number for it in existing_items), default=0)
        next_num = max(header_last_id, max_existing) + 1
        todo_id = f"TODO-{next_num:02d}"

        new_block = (
            f"### [{todo_id}] {clean_title}\n"
            f"- **建立日期**：{today_str}\n"
            f"- **目標範疇**：`{clean_scope}`\n"
            f"- **備忘與解法要點**：{clean_note}"
        )

        new_item = TodoItem(
            todo_id=todo_id,
            number=next_num,
            title=clean_title,
            date=today_str,
            scope=clean_scope,
            note=clean_note,
            raw_block=new_block,
        )

        updated_preamble = self._update_preamble_headers(
            preamble_lines, today_str=today_str, last_id=next_num, model=clean_model
        )
        all_blocks = [it.raw_block for it in existing_items] + [new_block]
        final_text = "\n".join(updated_preamble) + "\n\n" + "\n\n".join(all_blocks) + "\n"
        # 原子寫入：避免當目錄尚不存在且無寫入問題時才落檔，此處已通過前置驗證，直接建立目錄並寫入
        self.roadmap_dir.mkdir(parents=True, exist_ok=True)
        self.todo_file.write_text(final_text, encoding="utf-8")
        return new_item

    def list_todos(self, scope_keyword: Optional[str] = None) -> List[TodoItem]:
        """唯讀檢索 TODO.md 中所有活躍待辦，支援依 --scope 關鍵字過濾。"""
        if not self.todo_file.exists():
            return []
        content = self.todo_file.read_text(encoding="utf-8", errors="replace")
        _, _, items = self._parse_ledger(content)
        if scope_keyword and scope_keyword.strip():
            kw = scope_keyword.strip().lower()
            items = [
                it for it in items
                if kw in it.scope.lower()
                or kw in it.title.lower()
                or kw in it.note.lower()
                or kw in it.todo_id.lower()
            ]
        return items

    def format_todo_table(
        self,
        items: Optional[List[TodoItem]] = None,
        scope_keyword: Optional[str] = None,
    ) -> str:
        """格式化輸出 TODO.md 活躍待辦摘要表格。"""
        if items is None:
            items = self.list_todos(scope_keyword=scope_keyword)

        if not items:
            filter_note = f" (過濾條件: {scope_keyword})" if scope_keyword else ""
            return (
                f"[agents-workflow:todo] 目前尚無活躍之輕量待辦項目{filter_note}。\n"
                f"帳本路徑: {self.todo_file}\n"
                f"可透過 'python yscb.py agents-workflow todo add \"<標題>\" --scope \"<模組>\"' 單行免讀追加。"
            )

        col_w = 96
        divider = "=" * col_w
        header = f"{'編號':<10} | {'建立日期':<10} | {'目標範疇':<22} | {'待辦標題與備忘摘要'}"
        sub_divider = "-" * col_w

        rows = [divider, header, sub_divider]
        for it in items:
            scope_disp = it.scope if len(it.scope) <= 20 else it.scope[:17] + "..."
            date_disp = it.date[:10] if it.date else "未標註"
            title_note = f"{it.title}" + (f" ({it.note})" if it.note and it.note != "無" else "")
            if len(title_note) > 46:
                title_note = title_note[:43] + "..."
            rows.append(f"{it.todo_id:<10} | {date_disp:<10} | {scope_disp:<22} | {title_note}")

        rows.append(divider)
        return "\n".join(rows)

    def promote_todos(
        self,
        todo_ids: List[str],
        slug: Optional[str] = None,
        model: str = "Unknown",
        target_plan: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """
        自 plans/roadmap/TODO.md 原子剪切拔除 (Pop) 指定之 1~N 筆待辦條目，
        遷入新建或既有之計畫目錄下存為 todo.md，並自動初始化伴隨 changelog.md。
        """
        if not self.todo_file.exists():
            return {
                "success": False,
                "error": (
                    f"待辦帳本 '{self.todo_file}' 尚不存在，無法執行立項拔除。 "
                    f"[Fix Hint: 請先執行 'todo add' 建立待辦項目]"
                ),
            }

        if not todo_ids:
            return {
                "success": False,
                "error": (
                    "未指定任何欲立項之 TODO-ID。 "
                    "[Fix Hint: 請傳入至少一個待辦編號，如 'todo promote TODO-01 --slug fix_cli']"
                ),
            }

        req_nums: List[int] = []
        invalid_tokens: List[str] = []
        for raw_token in todo_ids:
            num = self.normalize_todo_num(raw_token)
            if num is None:
                invalid_tokens.append(str(raw_token))
            elif num not in req_nums:
                req_nums.append(num)

        if invalid_tokens:
            return {
                "success": False,
                "error": (
                    f"無效的待辦編號格式：{', '.join(invalid_tokens)}。 "
                    f"[Fix Hint: 請使用如 'TODO-01' 或 '01' 之格式]"
                ),
            }

        if not target_plan:
            clean_slug = (slug or "").strip()
            if not clean_slug or not self.SLUG_PATTERN.match(clean_slug):
                return {
                    "success": False,
                    "error": (
                        f"無效或缺失之 '--slug' 參數：'{slug or ''}'。 "
                        f"[Fix Hint: 請提供符合 '^[a-z0-9_]+$'（小寫英數與底線蛇形命名）之 --slug，例如 '--slug fix_parser_edge_case']"
                    ),
                }
        else:
            clean_slug = ""

        content = self.todo_file.read_text(encoding="utf-8", errors="replace")
        preamble_lines, header_last_id, existing_items = self._parse_ledger(content)
        existing_map = {it.number: it for it in existing_items}

        missing_nums = [n for n in req_nums if n not in existing_map]
        if missing_nums:
            missing_strs = ", ".join(f"TODO-{n:02d}" for n in missing_nums)
            avail_strs = ", ".join(it.todo_id for it in existing_items) if existing_items else "無可用待辦"
            return {
                "success": False,
                "error": (
                    f"於 TODO.md 中找不到指定之待辦編號：{missing_strs}（目前可用：{avail_strs}）。 "
                    f"[Fix Hint: 已保持 TODO.md 原子無損未修改，請先以 'todo list' 確認編號]"
                ),
            }

        clean_model = (model or "Unknown").strip() or "Unknown"
        if clean_model.startswith("[") and clean_model.endswith("]"):
            clean_model = "Unknown"
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 解析或建立目標計畫目錄
        if target_plan:
            from .plans.scanner import PlanScanner
            scanner = PlanScanner(plans_dir=self.plans_dir)
            resolved_dir, err = scanner.resolve_target_plan_dir(target_plan)
            if err or resolved_dir is None:
                return {
                    "success": False,
                    "error": f"{err or '找不到指定之目標計畫目錄'} [Fix Hint: 請確認 --plan 指定之目錄已存在於 plans/ 下]",
                }
            target_dir = resolved_dir
            # 若 target_plan 為子計畫目錄 (sub_*)，自動於父計畫之 umbrella_overview.md 補登子計畫名稱，防止 plan verify 產生未登記 WARN
            if target_dir.name.startswith("sub_"):
                umb_md = target_dir.parent / "umbrella_overview.md"
                if umb_md.is_file():
                    try:
                        u_text = umb_md.read_text(encoding="utf-8", errors="replace")
                        if target_dir.name not in u_text:
                            umb_md.write_text(
                                u_text.rstrip() + f"\n- `{target_dir.name}`\n",
                                encoding="utf-8",
                            )
                    except Exception:
                        pass
        else:
            now_prefix = datetime.now().strftime("%Y_%m_%d_%H%M")
            target_dir = (self.plans_dir / f"{now_prefix}_{clean_slug}").resolve()
            target_dir.mkdir(parents=True, exist_ok=True)

        promoted_items = [existing_map[n] for n in req_nums]
        remaining_items = [it for it in existing_items if it.number not in set(req_nums)]
        max_ever = max(header_last_id, max((it.number for it in existing_items), default=0))

        # 1. 原子寫回更新後之 TODO.md（保留單調計數器 max_ever 不倒退）
        updated_preamble = self._update_preamble_headers(
            preamble_lines, today_str=today_str, last_id=max_ever, model=None
        )
        if remaining_items:
            rem_text = (
                "\n".join(updated_preamble)
                + "\n\n"
                + "\n\n".join(it.raw_block for it in remaining_items)
                + "\n"
            )
        else:
            rem_text = "\n".join(updated_preamble) + "\n"
        self.todo_file.write_text(rem_text, encoding="utf-8")

        # 2. 寫入目標計畫目錄下之 todo.md
        dest_todo = target_dir / "todo.md"
        promoted_blocks_str = "\n\n".join(it.raw_block for it in promoted_items)
        if dest_todo.exists():
            existing_todo_content = dest_todo.read_text(encoding="utf-8", errors="replace").rstrip()
            dest_todo.write_text(existing_todo_content + "\n\n" + promoted_blocks_str + "\n", encoding="utf-8")
        else:
            todo_doc = (
                f"# 計畫前置待辦來源清單 (Promoted TODOs)\n\n"
                f"> 主題：{target_dir.name}  \n"
                f"> 建立日期：{today_str}  \n"
                f"> 狀態：Active  \n"
                f"> 模型：{clean_model}  \n\n"
                f"---\n\n"
                f"## 立項待辦條目 (Promoted Items)\n\n"
                f"{promoted_blocks_str}\n"
            )
            dest_todo.write_text(todo_doc, encoding="utf-8")

        promoted_id_strs = [it.todo_id for it in promoted_items]

        # 3. 自動初始化或追加伴隨 changelog.md
        from .plans.verifier import PlanVerifier
        verifier = PlanVerifier(plans_dir=self.plans_dir)
        verifier.append_changelog_entry(
            target_dir,
            summary=f"自 TODO.md 原子拔除立項 ({', '.join(promoted_id_strs)}) 遷入為 todo.md",
            log_type="PHASE",
            model=clean_model,
        )

        disp_plan = (
            f"{target_dir.parent.name}/{target_dir.name}"
            if target_dir.name.startswith("sub_") and target_dir.parent != self.plans_dir
            else target_dir.name
        )

        msg = (
            f"[agents-workflow:todo] [SUCCESS] 已完成待辦原子拔除並遷入計畫目錄：\n"
            f"  * 拔除待辦   : {', '.join(promoted_id_strs)} (已自 TODO.md 移除，最後分配編號維持 {max_ever})\n"
            f"  * 目標目錄   : {target_dir}\n"
            f"  * 遷入檔案   : {dest_todo.name} (+ changelog.md)\n"
            f"  * 當前狀態   : Seeded\n"
            f"  * [!] 下一步指引 : 請直接於該既有目錄 '{disp_plan}' 內原地建立 P00_discuss.md、fast_track_plan.md 或 revision_log.md，嚴禁重複新建第二個時間戳資料夾！"
        )

        return {
            "success": True,
            "plan_dir": target_dir,
            "plan_name": disp_plan,
            "todo_path": dest_todo,
            "promoted_ids": promoted_id_strs,
            "model": clean_model,
            "message": msg,
        }
