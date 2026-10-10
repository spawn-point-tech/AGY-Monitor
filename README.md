# 🛰️ AGY-Monitor

> **Real-Time Live Thought & Background Task Companion HUD for Google Antigravity (`agy`)**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-0%20(Pure%20Stdlib)-brightgreen.svg)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**AGY-Monitor** is a zero-dependency, real-time terminal HUD designed to run alongside [Google Antigravity](https://github.com) (`agy`). Open it in a split terminal pane, secondary monitor, or tmux window to stream internal Chain-of-Thought (CoT) reasoning, tool execution traces, and background task outputs live—without interrupting your prompt session or navigating menus.

---

## ⚡ Highlights

- 🪶 **Zero External Dependencies**: Built with 100% pure Python standard library (`sys`, `os`, `threading`, `textwrap`, `json`, `re`). No `pip install`, no `windows-curses`, no `textual`, and no C-extensions required.
- 💻 **True Cross-Platform**: Native support for **Windows** (PowerShell, Command Prompt, Windows Terminal, ConPTY), **macOS** (Terminal.app, iTerm2, Kitty, Ghostty), and **Linux** (bash, zsh).
- 🧠 **Dual Live Streaming**:
  - **Thought Stream**: Live streaming of Antigravity's internal reasoning and plan iterations.
  - **Task Stream**: Real-time auto-discovery and output tailing for background tasks (`task-*.log`).
- 🖥️ **3 Dynamic View Modes**:
  - `1`: **Split View** (Thoughts on top, Tasks on bottom with independent scroll focus).
  - `2`: **Full Thoughts View** (Maximized pane for deep reasoning and prompts).
  - `3`: **Full Tasks View** (Maximized pane for watching compilers, tests, linters, and servers).
- 🔄 **Smart Task Management**:
  - **Auto-Follow Mode**: Automatically locks onto and tails newly launched background tasks.
  - **Task Switcher**: Cycle between background tasks (`[` / `]`), or jump through currently running tasks with `Tab`.
  - **Status Badges**: Visual indicators for `RUNNING`, `FINISHED`, and `FAILED` tasks with exit codes and timestamps.
- 📐 **Dynamic Word Wrapping & Reflow**: Long thoughts and markdown explanations wrap cleanly based on current window width—no clipped text or ellipses in half-screen/tiled windows.
- 🔍 **Tool Call Filter**: Toggle tool calls on or off (`T`) to switch between pure distilled reasoning and complete execution traces.
- 🎨 **Flicker-Free Terminal UI**: Uses ANSI Alternate Screen Buffers (`\033[?1049h`), double-buffered frame diffing, solid inverse status bars, and cleans up seamlessly on exit (`Q`).
- ❓ **In-App Help Overlay**: Press `H` or `?` anytime for an interactive controls cheat sheet.

---

## 🚀 Quickstart

### Prerequisites
- Python 3.8 or newer (already installed on virtually all developer machines).

### 1. Clone the Repository
```bash
git clone https://github.com/techpoint/AGY-Monitor.git
cd AGY-Monitor
```

### 2. Run Directly
```bash
python agy_monitor.py
```

*AGY-Monitor automatically locates your active Antigravity session directory and begins streaming instantly.*

---

## 📦 Global Installation (Run Anywhere as `agy-monitor`)

To launch `agy-monitor` from any folder or terminal window:

### Windows (PowerShell / CMD)
Add this directory to your user `PATH`, or copy the launchers to your `bin` folder:
```powershell
# Option A: Copy to your existing user bin or agy directory
Copy-Item "agy_monitor.py", "agy-monitor.cmd", "agy-monitor.ps1" -Destination "$env:LOCALAPPDATA\agy\bin\"

# Option B: Add repository folder to user PATH
[Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";$PWD", "User")
```

Once added, simply type:
```powershell
agy-monitor
```

### macOS & Linux
Make the shell wrapper executable and symlink to `/usr/local/bin` or `~/.local/bin`:
```bash
chmod +x agy_monitor.py agy-monitor.sh
ln -s "$(pwd)/agy-monitor.sh" /usr/local/bin/agy-monitor
```

Once installed, simply run:
```bash
agy-monitor
```

---

## 🎮 Keyboard Controls

| Key | Action | Description |
|:---:|:---|:---|
| `1` | **Split View** | Split layout with Thoughts on top and Tasks on bottom. |
| `2` | **Full Thoughts** | Maximized layout dedicated to agent reasoning & plan. |
| `3` | **Full Tasks** | Maximized layout dedicated to background task logs. |
| `F` | **Toggle Focus** | Switches active scroll focus between Thoughts & Tasks in Split View. |
| `T` | **Toggle Tool Calls** | Show or hide tool action metadata in the Thought pane. |
| `[` or `←` | **Previous Task** | Switch active view to earlier background task in session. |
| `]` or `→` | **Next Task** | Switch active view to later background task in session. |
| `Tab` | **Cycle Running** | Jump directly between currently active `RUNNING` tasks. |
| `A` | **Auto-Follow** | Toggle automatic switching to the latest active task (`ON`/`OFF`). |
| `↑` / `↓` (or `K` / `J`) | **Scroll Lines** | Scroll active pane up or down line-by-line. |
| `PgUp` / `PgDn` | **Scroll Pages** | Page up / page down in active pane. |
| `End` / `Space` | **Jump to Latest** | Jump directly to latest line and resume live tailing. |
| `H` or `?` | **Help Overlay** | Toggle interactive on-screen controls reference. |
| `Q` or `Ctrl+C` | **Quit** | Cleanly exit and restore terminal screen buffer. |

---

## 🛠️ CLI Options

```text
usage: agy_monitor.py [-h] [--session SESSION] [--all] [--list]

Live Thought & Task Monitor for Antigravity (agy)

options:
  -h, --help            Show this help message and exit
  --session, -s SESSION Target a specific conversation session ID
  --all, -a             Replay entire session history from step 1
  --list, -l            List recent active conversation sessions
```

### Examples
- **Stream latest session automatically**:
  ```bash
  agy-monitor
  ```
- **List available sessions**:
  ```bash
  agy-monitor --list
  ```
- **Attach to a specific historical session**:
  ```bash
  agy-monitor --session 46ee0c97-229f-4925-afcc-6172f4275dcc
  ```
- **Replay complete conversation history**:
  ```bash
  agy-monitor --all
  ```

---

## 🏗️ Architecture & How It Works

```
┌────────────────────────────────────────────────────────┐
│               Google Antigravity CLI (agy)             │
│                                                        │
│  • Agent Engine ───► transcript_full.jsonl             │
│  • Background Tasks ─► .system_generated/tasks/*.log   │
└───────────────────────────┬────────────────────────────┘
                            │ Non-blocking read (passive)
                            ▼
┌────────────────────────────────────────────────────────┐
│                       AGY-Monitor                      │
│                                                        │
│  ┌────────────────────┐      ┌──────────────────────┐  │
│  │ TranscriptWatcher  │      │     TasksWatcher     │  │
│  │ (Background Thread)│      │ (Background Thread)  │  │
│  └─────────┬──────────┘      └──────────┬───────────┘  │
│            │                            │              │
│            └──────────► 🔒 ◄────────────┘              │
│                  MonitorState (RLock)                  │
│                           │                            │
│                           ▼                            │
│               TerminalRenderer (Main Thread)           │
│         Dynamic Word Reflow & Double-Buffered TUI      │
│                           │                            │
│                           ▼                            │
│               Alternate Screen Buffer                  │
└────────────────────────────────────────────────────────┘
```

1. **Non-Invasive Observer**: AGY-Monitor runs as an isolated process. It never injects code or takes locks on Antigravity's active database or transcript files.
2. **File Pointer Tracking**: Streams `transcript_full.jsonl` and task logs via persistent file pointer offsets, reading only incremental diffs to achieve sub-millisecond latency with near-zero CPU usage.
3. **Double Buffering**: Terminal frames are calculated entirely in memory and rendered using ANSI cursor positioning, completely eliminating screen flickering and jitter.
4. **Clean Restoration**: When you quit (`Q`), AGY-Monitor cleanly exits the alternate screen buffer (`\033[?1049l`) and restores your cursor, returning your terminal to its exact state prior to launching.

---

## 🤝 Contributing

Contributions, bug reports, and suggestions are welcome!
1. Fork the repository.
2. Create your feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'Add amazing feature'`).
4. Push to the branch (`git push origin feature/amazing-feature`).
5. Open a Pull Request.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details.
