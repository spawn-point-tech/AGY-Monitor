#!/usr/bin/env python3
"""
Antigravity Live Thought & Task Monitor (agy-monitor v2)
Real-time companion terminal HUD for Google Antigravity (agy).

Features:
- 100% Zero-Dependency (pure Python standard library).
- Cross-platform: Windows, macOS, Linux.
- Flicker-free Alternate Screen Buffer (clean exit restores terminal).
- 3 View Modes: Split Screen (Thoughts + Tasks), Full Thoughts, Full Tasks.
- Live background task log streaming & discovery (.system_generated/tasks/task-*.log).
- Interactive navigation: Task switching, Auto-Follow, scrolling, and in-app Help overlay (H).
"""

import os
import sys
import re
import time
import json
import shutil
import signal
import atexit
import argparse
import threading
import textwrap
from pathlib import Path
from datetime import datetime
from collections import deque

# Enable VT100 / ANSI escape sequences on Windows
if sys.platform == "win32":
    os.system("")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
else:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

# ANSI Codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
REVERSE = "\033[7m"

# Foreground Colors
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BRIGHT_WHITE = "\033[97m"
GRAY = "\033[90m"

# Background Colors
BG_DARK = "\033[40m"
BG_BLUE = "\033[44m"
BG_MAGENTA = "\033[45m"
BG_CYAN = "\033[46m"
BG_GRAY = "\033[100m"

# Alternate Screen Buffer Controls
ENTER_ALT_BUFFER = "\033[?1049h\033[?25l"
EXIT_ALT_BUFFER = "\033[?25h\033[?1049l\033[0m\n"
CLEAR_LINE = "\033[K"
CURSOR_HOME = "\033[H"

ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

def strip_ansi(s: str) -> str:
    """Return string stripped of all ANSI escape sequences."""
    return ANSI_REGEX.sub("", s)

def visible_len(s: str) -> int:
    """Calculate visible character length excluding ANSI sequences."""
    return len(strip_ansi(s))

def truncate_ansi(s: str, max_w: int) -> str:
    """Safely truncate string to visible max_w columns while keeping ANSI reset intact."""
    if visible_len(s) <= max_w:
        return s
    out = []
    cur_w = 0
    idx = 0
    while idx < len(s) and cur_w < max_w - 1:
        m = ANSI_REGEX.match(s, idx)
        if m:
            out.append(m.group(0))
            idx = m.end()
        else:
            out.append(s[idx])
            cur_w += 1
            idx += 1
    out.append("…")
    out.append(RESET)
    return "".join(out)

def make_inverse_bar(left_text: str, right_text: str, cols: int) -> str:
    """Build a solid inverse-styled status/title bar spanning exactly cols columns."""
    max_left = max(10, cols - visible_len(right_text) - 1)
    if visible_len(left_text) > max_left:
        left_text = truncate_ansi(left_text, max_left)
    pad = max(0, cols - visible_len(left_text) - visible_len(right_text))
    content = left_text + (" " * pad) + right_text
    safe_content = content.replace(RESET, RESET + REVERSE)
    return f"{REVERSE}{safe_content}{RESET}"

# Cross-Platform Keyboard Input
class KeyReader:
    def __init__(self):
        self.is_windows = sys.platform == "win32"
        self.old_settings = None
        if not self.is_windows:
            import termios
            import tty
            try:
                self.old_settings = termios.tcgetattr(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())
            except Exception:
                pass

    def cleanup(self):
        if not self.is_windows and self.old_settings is not None:
            import termios
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_settings)
            except Exception:
                pass

    def poll(self) -> str:
        """Non-blocking key read. Returns lowercase key token or empty string."""
        if self.is_windows:
            import msvcrt
            if not msvcrt.kbhit():
                return ""
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                ch2 = msvcrt.getch()
                if ch2 == b"H": return "up"
                if ch2 == b"P": return "down"
                if ch2 == b"K": return "left"
                if ch2 == b"M": return "right"
                if ch2 == b"I": return "pgup"
                if ch2 == b"Q": return "pgdn"
                if ch2 == b"G": return "home"
                if ch2 == b"O": return "end"
                return ""
            if ch == b"\x1b": return "esc"
            if ch == b"\t": return "tab"
            if ch in (b"\r", b"\n"): return "enter"
            if ch == b"\x03": return "ctrl_c"
            try:
                return ch.decode("utf-8", errors="ignore").lower()
            except Exception:
                return ""
        else:
            import select
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if not r:
                return ""
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                r2, _, _ = select.select([sys.stdin], [], [], 0.05)
                if not r2:
                    return "esc"
                seq = sys.stdin.read(1)
                if seq == "[":
                    code = sys.stdin.read(1)
                    if code == "A": return "up"
                    if code == "B": return "down"
                    if code == "C": return "right"
                    if code == "D": return "left"
                    if code == "5":
                        sys.stdin.read(1) # consume ~
                        return "pgup"
                    if code == "6":
                        sys.stdin.read(1) # consume ~
                        return "pgdn"
                    if code == "H": return "home"
                    if code == "F": return "end"
                return "esc"
            if ch == "\t": return "tab"
            if ch in ("\r", "\n"): return "enter"
            if ch == "\x03": return "ctrl_c"
            return ch.lower()

def get_base_brain_dir() -> Path:
    """Dynamically locate the Antigravity brain directory without hardcoding usernames."""
    if os.environ.get("ANTIGRAVITY_BRAIN_DIR"):
        p = Path(os.environ["ANTIGRAVITY_BRAIN_DIR"])
        if p.exists():
            return p

    candidates = [Path.home()]
    if os.environ.get("USERPROFILE"):
        candidates.append(Path(os.environ["USERPROFILE"]))
    if os.environ.get("HOME"):
        candidates.append(Path(os.environ["HOME"]))

    for base in candidates:
        brain_path = base / ".gemini" / "antigravity-cli" / "brain"
        if brain_path.exists():
            return brain_path

    return Path.home() / ".gemini" / "antigravity-cli" / "brain"

def find_latest_session(brain_dir: Path) -> Path:
    """Find the most recently modified conversation session folder."""
    if not brain_dir.exists():
        raise FileNotFoundError(f"Antigravity brain directory not found: {brain_dir}")

    sessions = []
    for entry in brain_dir.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            log_file = entry / ".system_generated" / "logs" / "transcript_full.jsonl"
            if log_file.exists():
                sessions.append((log_file.stat().st_mtime, entry, log_file))

    if not sessions:
        raise FileNotFoundError(f"No active session logs found in {brain_dir}")

    sessions.sort(key=lambda s: s[0], reverse=True)
    return sessions[0][1]

class TaskRecord:
    def __init__(self, task_id: str, num_id: int, log_path: Path):
        self.task_id = task_id
        self.num_id = num_id
        self.log_path = log_path
        self.command = "Unknown command"
        self.summary = ""
        self.status = "RUNNING"
        self.exit_code = None
        self.lines = deque(maxlen=2000)
        self.last_read_pos = 0
        self.mtime = 0.0

class MonitorState:
    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.log_file = session_dir / ".system_generated" / "logs" / "transcript_full.jsonl"
        self.tasks_dir = session_dir / ".system_generated" / "tasks"

        # View Modes: 1 = SPLIT, 2 = THOUGHTS, 3 = TASKS
        self.mode = 1
        self.show_help = False
        self.running = True

        # Thoughts Data
        self.thought_events = deque(maxlen=2000)
        self.thought_scroll_offset = 0 # 0 = bottom / live auto-scroll
        self.show_tools = True # Toggle tool calls in thoughts stream with 'T'
        self.lock = threading.RLock()

        # Tasks Data
        self.tasks = {} # task_id -> TaskRecord
        self.task_order = [] # list of task_ids sorted chronologically
        self.selected_task_id = None
        self.task_auto_follow = True
        self.task_scroll_offset = 0 # 0 = bottom / live auto-scroll

        # Status & Stats
        self.step_count = 0
        self.last_step_time = ""
        self.status_msg = "Connected"
        self.split_focus = "tasks"  # "tasks" or "thoughts"

    def add_event(self, ev_data: dict):
        with self.lock:
            self.thought_events.append(ev_data)

    def add_thought_block(self, lines: list, ev_type: str = "THOUGHT"):
        with self.lock:
            self.thought_events.append({"type": ev_type, "paragraphs": lines})

    def get_or_create_task(self, task_id: str, log_path: Path = None) -> TaskRecord:
        if task_id in self.tasks:
            return self.tasks[task_id]
        m = re.search(r"(\d+)", task_id)
        num_id = int(m.group(1)) if m else 0
        if log_path is None:
            log_path = self.tasks_dir / f"{task_id}.log"
        record = TaskRecord(task_id, num_id, log_path)
        self.tasks[task_id] = record
        self.task_order.append(task_id)
        self.task_order.sort(key=lambda tid: self.tasks[tid].num_id)

        if self.task_auto_follow:
            self.selected_task_id = task_id
            self.task_scroll_offset = 0

        return record

class TranscriptWatcher(threading.Thread):
    def __init__(self, state: MonitorState, replay_all: bool = False):
        super().__init__(daemon=True)
        self.state = state
        self.replay_all = replay_all

    def format_ts(self, ts_str: str) -> str:
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            return dt.strftime("%H:%M:%S")
        except Exception:
            return ts_str or ""

    def run(self):
        log_file = self.state.log_file
        while not log_file.exists() and self.state.running:
            time.sleep(0.3)

        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            if not self.replay_all:
                f_size = log_file.stat().st_size
                seek_pos = max(0, f_size - 40000)
                f.seek(seek_pos)
                if seek_pos > 0:
                    f.readline()
            else:
                f.seek(0)

            processed_steps = set()

            while self.state.running:
                line = f.readline()
                if line:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        data = json.loads(line_str)
                    except json.JSONDecodeError:
                        continue

                    self.process_entry(data, processed_steps)
                else:
                    time.sleep(0.15)

    def process_entry(self, data: dict, processed_steps: set):
        step = data.get("step_index", "?")
        step_type = data.get("type", "")
        ts = self.format_ts(data.get("created_at", ""))
        thinking = data.get("thinking")
        tool_calls = data.get("tool_calls")
        content = data.get("content")

        if step != "?":
            self.state.step_count = step
            self.state.last_step_time = ts

        # 1. Parse Thinking / CoT
        if thinking and step not in processed_steps:
            processed_steps.add(step)
            self.state.add_event({
                "type": "THOUGHT",
                "step": step,
                "ts": ts,
                "paragraphs": thinking.splitlines()
            })

        # 2. Parse Tool Calls
        if tool_calls and isinstance(tool_calls, list):
            for tc in tool_calls:
                name = tc.get("name", "tool")
                args = tc.get("args", {})
                summary = args.get("toolSummary") or args.get("summary") or args.get("toolAction") or ""
                details = []
                if "CommandLine" in args:
                    details.append(("Cmd", args["CommandLine"]))
                elif "TargetFile" in args:
                    details.append(("File", args["TargetFile"]))
                elif "AbsolutePath" in args:
                    details.append(("File", args["AbsolutePath"]))

                self.state.add_event({
                    "type": "TOOL",
                    "name": name,
                    "summary": summary,
                    "details": details
                })

        # 3. Detect background task launches and completions in content
        if content and isinstance(content, str):
            # Check for background task launch
            launch_match = re.search(r"task id:\s*([a-zA-Z0-9_-]+/)?(task-\d+)", content)
            if launch_match:
                task_id = launch_match.group(2)
                with self.state.lock:
                    rec = self.state.get_or_create_task(task_id)
                    rec.status = "RUNNING"

            # Check for task completion
            finish_match = re.search(r'sender=.*?/(task-\d+).*?exited with code\s*(\d+)', content)
            if finish_match:
                task_id = finish_match.group(1)
                code = int(finish_match.group(2))
                with self.state.lock:
                    if task_id in self.state.tasks:
                        rec = self.state.tasks[task_id]
                        rec.exit_code = code
                        rec.status = f"DONE ({code})" if code == 0 else f"EXIT ({code})"

            # User prompt step
            if step_type == "USER_INPUT":
                self.state.add_event({
                    "type": "USER",
                    "step": step,
                    "ts": ts,
                    "paragraphs": content.strip().splitlines()
                })

class TasksWatcher(threading.Thread):
    def __init__(self, state: MonitorState):
        super().__init__(daemon=True)
        self.state = state

    def run(self):
        tasks_dir = self.state.tasks_dir
        while self.state.running:
            if tasks_dir.exists():
                try:
                    for f in tasks_dir.glob("task-*.log"):
                        tid = f.stem
                        with self.state.lock:
                            rec = self.state.get_or_create_task(tid, f)
                            rec.mtime = f.stat().st_mtime

                        # Read newly appended lines for this task
                        self.read_task_log(rec)
                except Exception:
                    pass
            time.sleep(0.2)

    def read_task_log(self, record: TaskRecord):
        try:
            if not record.log_path.exists():
                return
            size = record.log_path.stat().st_size
            if size < record.last_read_pos:
                record.last_read_pos = 0 # reset on file truncate
            if size > record.last_read_pos:
                with open(record.log_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(record.last_read_pos)
                    for line in f:
                        clean_line = line.rstrip("\r\n")
                        with self.state.lock:
                            record.lines.append(clean_line)
                    record.last_read_pos = f.tell()
        except Exception:
            pass

class TerminalRenderer:
    def __init__(self, state: MonitorState):
        self.state = state
        self.key_reader = KeyReader()
        self.last_size = (0, 0)
        self.setup_terminal()

    def setup_terminal(self):
        sys.stdout.write(ENTER_ALT_BUFFER)
        sys.stdout.flush()
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def cleanup(self):
        try:
            self.key_reader.cleanup()
            sys.stdout.write(EXIT_ALT_BUFFER)
            sys.stdout.flush()
        except Exception:
            pass

    def signal_handler(self, sig, frame):
        self.state.running = False
        self.cleanup()
        sys.exit(0)

    def run(self):
        while self.state.running:
            try:
                key = self.key_reader.poll()
                if key:
                    self.handle_key(key)

                self.draw_frame()
            except Exception:
                pass
            time.sleep(0.04)

    def handle_key(self, key: str):
        if not key:
            return
        key = key.lower()

        if key in ("q", "ctrl_c"):
            self.state.running = False
            return

        if key in ("h", "?"):
            self.state.show_help = not self.state.show_help
            return

        if self.state.show_help:
            # Any key dismisses help
            self.state.show_help = False
            return

        if key == "1":
            self.state.mode = 1
        elif key == "2":
            self.state.mode = 2
        elif key == "3":
            self.state.mode = 3
        elif key == "f":
            if self.state.mode == 1:
                with self.state.lock:
                    self.state.split_focus = "thoughts" if self.state.split_focus == "tasks" else "tasks"
        elif key == "t":
            with self.state.lock:
                self.state.show_tools = not self.state.show_tools
                self.state.thought_scroll_offset = 0
        elif key == "a":
            with self.state.lock:
                self.state.task_auto_follow = not self.state.task_auto_follow
                if self.state.task_auto_follow and self.state.task_order:
                    self.state.selected_task_id = self.state.task_order[-1]
                    self.state.task_scroll_offset = 0
        elif key in ("[", "left"):
            self.navigate_task(direction=-1)
        elif key in ("]", "right"):
            self.navigate_task(direction=1)
        elif key == "tab":
            self.cycle_running_task()
        elif key in ("up", "k"):
            self.scroll_active_pane(delta=1)
        elif key in ("down", "j"):
            self.scroll_active_pane(delta=-1)
        elif key == "pgup":
            self.scroll_active_pane(delta=8)
        elif key == "pgdn":
            self.scroll_active_pane(delta=-8)
        elif key in ("end", " ", "g"):
            with self.state.lock:
                self.state.thought_scroll_offset = 0
                self.state.task_scroll_offset = 0

    def navigate_task(self, direction: int):
        with self.state.lock:
            if not self.state.task_order:
                return
            # Manual navigation pauses auto-follow
            self.state.task_auto_follow = False
            cur_id = self.state.selected_task_id
            if cur_id in self.state.task_order:
                idx = self.state.task_order.index(cur_id)
                new_idx = max(0, min(len(self.state.task_order) - 1, idx + direction))
            else:
                new_idx = len(self.state.task_order) - 1
            self.state.selected_task_id = self.state.task_order[new_idx]
            self.state.task_scroll_offset = 0

    def cycle_running_task(self):
        with self.state.lock:
            running_tasks = [tid for tid in self.state.task_order if self.state.tasks[tid].status == "RUNNING"]
            if not running_tasks:
                return
            cur_id = self.state.selected_task_id
            if cur_id in running_tasks:
                idx = (running_tasks.index(cur_id) + 1) % len(running_tasks)
            else:
                idx = 0
            self.state.selected_task_id = running_tasks[idx]
            self.state.task_scroll_offset = 0

    def scroll_active_pane(self, delta: int):
        cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        available_rows = rows - 2
        with self.state.lock:
            thought_len = len(self.get_rendered_thought_lines(cols))
            if self.state.mode == 1:
                if self.state.split_focus == "thoughts":
                    max_lines = max(4, int(available_rows * 0.52))
                    max_offset = max(0, thought_len - max_lines)
                    self.state.thought_scroll_offset = max(0, min(max_offset, self.state.thought_scroll_offset + delta))
                else:
                    top_h = max(4, int(available_rows * 0.52))
                    bottom_h = max(3, available_rows - top_h - 1)
                    rec = self.state.tasks.get(self.state.selected_task_id)
                    total_lines = len(rec.lines) if rec else 0
                    max_offset = max(0, total_lines - bottom_h)
                    self.state.task_scroll_offset = max(0, min(max_offset, self.state.task_scroll_offset + delta))
            elif self.state.mode == 2:
                max_offset = max(0, thought_len - available_rows)
                self.state.thought_scroll_offset = max(0, min(max_offset, self.state.thought_scroll_offset + delta))
            elif self.state.mode == 3:
                rec = self.state.tasks.get(self.state.selected_task_id)
                total_lines = len(rec.lines) if rec else 0
                max_offset = max(0, total_lines - available_rows)
                self.state.task_scroll_offset = max(0, min(max_offset, self.state.task_scroll_offset + delta))

    def draw_frame(self):
        cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        cur_size = (cols, rows)
        resized = False
        if cur_size != self.last_size:
            self.last_size = cur_size
            resized = True

        frame_lines = []

        # 1. Top Header Bar (Inverse)
        pane_title = "THOUGHTS" if self.state.mode in (1, 2) else "TASKS"
        tools_tag = f" [TOOLS: ON]" if self.state.show_tools else f" {YELLOW}[TOOLS: HIDDEN]{RESET}"
        tools_str = tools_tag if self.state.mode in (1, 2) else ""
        sess_name = self.state.session_dir.name[:18]
        header_left = f" AGY-MONITOR │ {BOLD}{pane_title}{RESET}{tools_str}"
        mode_badge = "[1: SPLIT]" if self.state.mode == 1 else ("[2: FULL THOUGHTS]" if self.state.mode == 2 else "[3: FULL TASKS]")
        header_right = f"Session: {sess_name}... │ {mode_badge} │ {BOLD}[H: Help]{RESET} "
        frame_lines.append(make_inverse_bar(header_left, header_right, cols))

        # 2. Main Content Views
        available_rows = rows - 2
        if self.state.mode == 1:
            frame_lines.extend(self.render_split_view(cols, available_rows))
        elif self.state.mode == 2:
            frame_lines.extend(self.render_thoughts_view(cols, available_rows))
        elif self.state.mode == 3:
            frame_lines.extend(self.render_tasks_view(cols, available_rows))

        # 3. Bottom Footer Status Bar (Inverse)
        af_badge = f"{GREEN}AUTO-FOLLOW: ON{RESET}" if self.state.task_auto_follow else f"{YELLOW}AUTO-FOLLOW: OFF (A){RESET}"
        tools_badge = f"{GREEN}TOOLS: ON (T){RESET}" if self.state.show_tools else f"{YELLOW}TOOLS: OFF (T){RESET}"
        focus_badge = f"{BOLD}FOCUS: THOUGHTS (F){RESET}" if self.state.split_focus == "thoughts" else f"{BOLD}FOCUS: TASKS (F){RESET}"
        mode_focus = f"│ {focus_badge} " if self.state.mode == 1 else ""
        footer_left = f" {BOLD}[1]{RESET} Split  {BOLD}[2]{RESET} Thoughts  {BOLD}[3]{RESET} Tasks {mode_focus}│ {tools_badge} │ {af_badge} │ {BOLD}[H]{RESET} Help"
        footer_right = f"{BOLD}[Q]{RESET} Quit "
        frame_lines.append(make_inverse_bar(footer_left, footer_right, cols))

        # 4. Optional Help Overlay Modal
        if self.state.show_help:
            frame_lines = self.overlay_help(frame_lines, cols, rows)

        # 5. Flush to Terminal (Full wipe on window resize)
        if resized:
            output_buffer = ["\033[2J\033[H"]
        else:
            output_buffer = [CURSOR_HOME]

        for idx, line in enumerate(frame_lines[:rows]):
            output_buffer.append(truncate_ansi(line, cols) + CLEAR_LINE)
            if idx < rows - 1:
                output_buffer.append("\n")

        sys.stdout.write("".join(output_buffer))
        sys.stdout.flush()

    def render_split_view(self, cols: int, height: int) -> list:
        lines = []
        top_h = max(2, int(height * 0.52))
        divider_h = 1
        bottom_h = max(1, height - top_h - divider_h)

        # Top Pane: Thoughts
        lines.extend(self.slice_thought_lines(cols, top_h))

        # Divider Bar: Tasks Breadcrumbs & Status (Inverse)
        with self.state.lock:
            total_tasks = len(self.state.task_order)
            running_tasks = sum(1 for tid in self.state.task_order if self.state.tasks[tid].status == "RUNNING")
            cur_id = self.state.selected_task_id or (self.state.task_order[-1] if self.state.task_order else "None")
            cur_rec = self.state.tasks.get(cur_id)
            status_str = f"[{cur_rec.status}]" if cur_rec else "[IDLE]"
            status_color = GREEN if "RUN" in status_str else (YELLOW if "0" in status_str else RED)
            focus_is_tasks = (self.state.split_focus == "tasks")
            cur_offset = self.state.task_scroll_offset if focus_is_tasks else self.state.thought_scroll_offset

        focus_indicator = f"{BOLD}★ TASKS [FOCUSED]{RESET}" if focus_is_tasks else f"{BOLD}▲ THOUGHTS [FOCUSED]{RESET}"
        task_info = f"{BOLD}{cur_id}{RESET} {status_color}{status_str}{RESET}"
        scroll_indicator = f"{YELLOW}[+{cur_offset} lines | Space: live]{RESET} " if cur_offset > 0 else ""
        bar_left = f" {focus_indicator} {GRAY}(F: switch focus){RESET} │ {task_info} {scroll_indicator}"
        bar_right = f"TASKS: {running_tasks} RUN / {total_tasks} TOTAL │ [←/→ task] "
        lines.append(make_inverse_bar(bar_left, bar_right, cols))

        # Bottom Pane: Selected Task Log
        lines.extend(self.slice_task_lines(cur_id, cols, bottom_h))
        return lines

    def render_thoughts_view(self, cols: int, height: int) -> list:
        return self.slice_thought_lines(cols, height)

    def render_tasks_view(self, cols: int, height: int) -> list:
        lines = []
        sidebar_w = min(28, max(18, cols // 4))
        content_w = cols - sidebar_w - 1

        with self.state.lock:
            tasks_list = list(reversed(self.state.task_order))
            cur_id = self.state.selected_task_id

        # Get task log lines
        task_content = self.slice_task_lines(cur_id, content_w, height)

        for row_idx in range(height):
            # Left Sidebar Item
            if row_idx < len(tasks_list):
                tid = tasks_list[row_idx]
                rec = self.state.tasks.get(tid)
                is_sel = (tid == cur_id)
                st = rec.status if rec else "RUNNING"
                st_badge = f"{GREEN}RUN{RESET}" if "RUN" in st else (f"{GRAY}0{RESET}" if "0" in st else f"{RED}ERR{RESET}")
                marker = f"{BOLD}{CYAN}▶{RESET}" if is_sel else " "
                item_str = f"{marker} {BOLD if is_sel else ''}{tid[:10]}{RESET} [{st_badge}]"
                pad = max(0, sidebar_w - visible_len(item_str))
                left_cell = item_str + (" " * pad)
            else:
                left_cell = " " * sidebar_w

            right_cell = task_content[row_idx] if row_idx < len(task_content) else ""
            lines.append(f"{left_cell}{GRAY}│{RESET}{right_cell}")

        return lines

    def get_rendered_thought_lines(self, width: int) -> list:
        wrap_w = max(20, width - 4)
        lines = []
        with self.state.lock:
            show_tools = self.state.show_tools
            events = list(self.state.thought_events)

        for ev in events:
            ev_type = ev.get("type")
            if ev_type == "TOOL" and not show_tools:
                continue

            if ev_type == "THOUGHT":
                step = ev.get("step", "?")
                ts = ev.get("ts", "")
                lines.append(f"{BOLD}{MAGENTA}[STEP {step}] REASONING{RESET} {GRAY}({ts}){RESET}")
                lines.append(f"{GRAY}{'-' * min(wrap_w, 60)}{RESET}")
                for p in ev.get("paragraphs", []):
                    if not p.strip():
                        lines.append("")
                    else:
                        for wl in textwrap.wrap(p, width=wrap_w, break_long_words=True, break_on_hyphens=False):
                            lines.append(f"  {BRIGHT_WHITE}{wl}{RESET}")
                lines.append(f"{GRAY}{'-' * min(wrap_w, 60)}{RESET}")
                lines.append("")

            elif ev_type == "TOOL":
                name = ev.get("name", "tool")
                summary = ev.get("summary", "")
                lines.append(f"  {BOLD}{CYAN}TOOL:{RESET} {BOLD}{name}{RESET} {YELLOW}({summary}){RESET}")
                for label, val in ev.get("details", []):
                    val_wrapped = textwrap.wrap(val, width=max(15, wrap_w - 10), break_long_words=True, break_on_hyphens=False)
                    if val_wrapped:
                        lines.append(f"     {GRAY}{label}:{RESET} {val_wrapped[0]}")
                        for extra in val_wrapped[1:]:
                            lines.append(f"     {' ' * (len(label) + 2)}{extra}")
                lines.append("")

            elif ev_type == "USER":
                step = ev.get("step", "?")
                ts = ev.get("ts", "")
                lines.append(f"{BOLD}{GREEN}[USER PROMPT - STEP {step}]{RESET} {GRAY}({ts}){RESET}")
                for p in ev.get("paragraphs", []):
                    for wl in textwrap.wrap(p, width=wrap_w, break_long_words=True, break_on_hyphens=False):
                        lines.append(f"  {WHITE}{wl}{RESET}")
                lines.append("")

        return lines

    def slice_thought_lines(self, width: int, max_lines: int) -> list:
        raw = self.get_rendered_thought_lines(width)
        offset = self.state.thought_scroll_offset

        if not raw:
            msg = "Waiting for reasoning or actions from Antigravity session..." if self.state.show_tools else "No thoughts to show (Tool calls hidden - press 'T' to show)..."
            return [f"  {GRAY}{msg}{RESET}"] + [""] * (max_lines - 1)

        end_idx = len(raw) - offset if offset > 0 else len(raw)
        start_idx = max(0, end_idx - max_lines)
        sliced = raw[start_idx:end_idx]

        while len(sliced) < max_lines:
            sliced.insert(0, "")
        return sliced

    def slice_task_lines(self, task_id: str, width: int, max_lines: int) -> list:
        with self.state.lock:
            rec = self.state.tasks.get(task_id) if task_id else None
            offset = self.state.task_scroll_offset
            if rec:
                raw = list(rec.lines)
            else:
                raw = []

        if not rec:
            return [f"  {GRAY}No task selected or no active background tasks recorded yet.{RESET}"] + [""] * (max_lines - 1)

        if not raw:
            return [f"  {GRAY}[{task_id}] Log file is empty or starting execution...{RESET}"] + [""] * (max_lines - 1)

        end_idx = len(raw) - offset if offset > 0 else len(raw)
        start_idx = max(0, end_idx - max_lines)
        sliced = raw[start_idx:end_idx]

        while len(sliced) < max_lines:
            sliced.insert(0, "")
        return [f"  {WHITE}{l}{RESET}" for l in sliced]

    def overlay_help(self, frame_lines: list, cols: int, rows: int) -> list:
        help_box = [
            "┌─────────────────────────────────────────────────────────────┐",
            "│                    AGY-MONITOR CONTROLS                     │",
            "├─────────────────────────────────────────────────────────────┤",
            "│  1          Split View (Thoughts on top, Tasks on bottom)   │",
            "│  2          Full Thoughts View                              │",
            "│  3          Full Tasks View                                 │",
            "│  f          Toggle focus: Thoughts <-> Tasks (Split View)   │",
            "│  t          Toggle Tool Calls: Show / Hide in thoughts      │",
            "│  [ or Left  Previous Task in history                        │",
            "│  ] or Right Next Task in history                            │",
            "│  Tab        Cycle through RUNNING tasks only                │",
            "│  a          Toggle Auto-Follow newest task (ON/OFF)         │",
            "│  Up / Down  Scroll active pane up / down (or k / j)         │",
            "│  PgUp/PgDn  Page scroll active pane                         │",
            "│  End/Space  Jump to latest line (resume live auto-scroll)   │",
            "│  h or ?     Toggle this Help screen                         │",
            "│  q          Quit monitor cleanly                            │",
            "└─────────────────────────────────────────────────────────────┘"
        ]
        box_h = len(help_box)
        box_w = visible_len(help_box[0])
        start_r = max(1, (rows - box_h) // 2)
        start_c = max(1, (cols - box_w) // 2)

        out = list(frame_lines)
        for i, line in enumerate(help_box):
            r = start_r + i
            if r < len(out):
                left_pad = " " * start_c
                out[r] = left_pad + f"{BOLD}{YELLOW}{line}{RESET}"
        return out

def main():
    parser = argparse.ArgumentParser(description="Live Thought & Task Monitor for Antigravity (agy)")
    parser.add_argument("--session", "-s", type=str, default=None, help="Target specific session ID")
    parser.add_argument("--all", "-a", action="store_true", help="Replay entire session history from step 1")
    parser.add_argument("--list", "-l", action="store_true", help="List recent active conversation sessions")
    args = parser.parse_args()

    brain_dir = get_base_brain_dir()

    if args.list:
        print(f"\n{BOLD}Active Antigravity Sessions in {brain_dir}:{RESET}\n")
        count = 0
        for entry in sorted(brain_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if entry.is_dir() and not entry.name.startswith("."):
                log_file = entry / ".system_generated" / "logs" / "transcript_full.jsonl"
                if log_file.exists():
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    size_kb = log_file.stat().st_size / 1024
                    print(f"  • {CYAN}{entry.name}{RESET}  {DIM}(Modified: {mtime}, Size: {size_kb:.1f} KB){RESET}")
                    count += 1
                    if count >= 10:
                        break
        print()
        return

    try:
        if args.session:
            session_dir = brain_dir / args.session
        else:
            session_dir = find_latest_session(brain_dir)

        state = MonitorState(session_dir)

        # Launch background watcher threads
        tw = TranscriptWatcher(state, replay_all=args.all)
        tw.start()

        kw = TasksWatcher(state)
        kw.start()

        # Run UI renderer on main thread
        renderer = TerminalRenderer(state)
        renderer.run()

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n\033[31mError:{RESET} {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
