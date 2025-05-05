import flet as ft
import subprocess
import os
import sys
import platform
import threading
import queue
import traceback
import asyncio
import psutil
from typing import Optional, TYPE_CHECKING, Tuple

# Import the color parser and AppState/ManagedProcessState
from .color_parser import parse_log_line_to_spans

if TYPE_CHECKING:
    from .state import AppState
from .utils import show_snackbar, update_page_safe  # Add import here

# --- Helper Function to Update Button States (Mostly Unchanged for now) --- #


def update_buttons_state(page: Optional[ft.Page], app_state: "AppState", is_running: bool):
    """Updates the state (text, icon, color, on_click) of the console button."""
    console_button = app_state.console_action_button
    needs_update = False

    # --- Define Button Actions (Point to adapted functions) --- #
    # start_action = lambda _: start_bot_and_show_console(page, app_state) if page else None
    # stop_action = lambda _: stop_bot_process(page, app_state) if page else None # stop_bot_process now calls stop_managed_process
    def _start_action(_):
        if page:
            start_bot_and_show_console(page, app_state)

    def _stop_action(_):
        if page:
            stop_bot_process(page, app_state)

    if console_button:
        button_text_control = console_button.content if isinstance(console_button.content, ft.Text) else None
        if button_text_control:
            if is_running:
                new_text = "停止 MaiCore"
                new_color = ft.colors.with_opacity(0.6, ft.colors.RED_ACCENT_100)
                new_onclick = _stop_action  # Use def
                if (
                    button_text_control.value != new_text
                    or console_button.bgcolor != new_color
                    or console_button.on_click != new_onclick
                ):
                    button_text_control.value = new_text
                    console_button.bgcolor = new_color
                    console_button.on_click = new_onclick
                    needs_update = True
            else:
                new_text = "启动 MaiCore"
                new_color = ft.colors.with_opacity(0.6, ft.colors.GREEN_ACCENT_100)
                new_onclick = _start_action  # Use def
                if (
                    button_text_control.value != new_text
                    or console_button.bgcolor != new_color
                    or console_button.on_click != new_onclick
                ):
                    button_text_control.value = new_text
                    console_button.bgcolor = new_color
                    console_button.on_click = new_onclick
                    needs_update = True
        else:
            print("[Update Buttons] Warning: console_action_button content is not Text?")

    if needs_update and page:
        print(f"[Update Buttons] State changed, triggering page update. is_running={is_running}")
        # from .utils import update_page_safe # Moved import to top
        page.run_task(update_page_safe, page)


# --- Generic Process Termination Helper ---
def _terminate_process_gracefully(process_id: str, handle: Optional[subprocess.Popen], pid: Optional[int]):
    """Helper to attempt graceful termination, then kill."""
    stopped_cleanly = False
    if handle and pid:
        print(f"[_terminate] Attempting termination using handle for PID: {pid} (ID: {process_id})...", flush=True)
        try:
            if handle.poll() is None:
                handle.terminate()
                print(f"[_terminate] Sent terminate() to PID: {pid}. Waiting briefly...", flush=True)
                try:
                    handle.wait(timeout=1.0)
                    print(f"[_terminate] Process PID: {pid} stopped after terminate().", flush=True)
                    stopped_cleanly = True
                except subprocess.TimeoutExpired:
                    print(f"[_terminate] Terminate timed out for PID: {pid}. Attempting kill()...", flush=True)
                    try:
                        handle.kill()
                        print(f"[_terminate] Sent kill() to PID: {pid}.", flush=True)
                    except Exception as kill_err:
                        print(f"[_terminate] Error during kill() for PID: {pid}: {kill_err}", flush=True)
            else:
                print("[_terminate] Process poll() was not None before terminate (already stopped?).", flush=True)
                stopped_cleanly = True  # Already stopped
        except Exception as e:
            print(f"[_terminate] Error during terminate/wait for PID: {pid}: {e}", flush=True)
    elif pid:
        print(
            f"[_terminate] No process handle, attempting psutil fallback for PID: {pid} (ID: {process_id})...",
            flush=True,
        )
        try:
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                    stopped_cleanly = True
                except psutil.TimeoutExpired:
                    proc.kill()
                print(f"[_terminate] psutil terminated/killed PID {pid}.", flush=True)
            else:
                print(f"[_terminate] psutil confirms PID {pid} does not exist.", flush=True)
                stopped_cleanly = True  # Already gone
        except Exception as ps_err:
            print(f"[_terminate] Error during psutil fallback for PID {pid}: {ps_err}", flush=True)
    else:
        print(f"[_terminate] Cannot terminate process ID '{process_id}': No handle or PID provided.", flush=True)
        stopped_cleanly = True  # Nothing to stop

    return stopped_cleanly


# --- Process Management Functions (Refactored for Multi-Process) --- #


def cleanup_on_exit(app_state: "AppState"):
    """Registered with atexit to ensure ALL managed processes are killed on script exit."""
    print("--- [atexit Cleanup] Running cleanup function ---", flush=True)
    # Iterate through a copy of the keys to avoid modification issues
    process_ids = list(app_state.managed_processes.keys())
    print(f"[atexit Cleanup] Found managed process IDs: {process_ids}", flush=True)

    for process_id in process_ids:
        process_state = app_state.managed_processes.get(process_id)
        if process_state and process_state.pid:
            print(f"[atexit Cleanup] Checking PID: {process_state.pid} for ID: {process_id}...", flush=True)
            try:
                # Use psutil directly as handles might be invalid in atexit
                if psutil.pid_exists(process_state.pid):
                    print(
                        f"[atexit Cleanup] PID {process_state.pid} exists. Attempting termination/kill...", flush=True
                    )
                    proc = psutil.Process(process_state.pid)
                    proc.terminate()
                    try:
                        proc.wait(timeout=0.5)
                    except psutil.TimeoutExpired:
                        proc.kill()
                    print(
                        f"[atexit Cleanup] psutil terminate/kill signal sent for PID {process_state.pid}.", flush=True
                    )
                else:
                    print(f"[atexit Cleanup] PID {process_state.pid} does not exist.", flush=True)
            except psutil.NoSuchProcess:
                print(f"[atexit Cleanup] psutil.NoSuchProcess error checking PID {process_state.pid}.", flush=True)
            except Exception as ps_err:
                print(f"[atexit Cleanup] Error cleaning up PID {process_state.pid}: {ps_err}", flush=True)
        elif process_state:
            print(f"[atexit Cleanup] Process ID '{process_id}' has no PID stored.", flush=True)
        # else: Process ID might have been removed already

    print("--- [atexit Cleanup] Cleanup function finished ---", flush=True)


def handle_disconnect(page: Optional[ft.Page], app_state: "AppState", e):
    """Handles UI disconnect. Sets the stop_event for the main bot.py process FOR NOW."""
    # TODO: In a full multi-process model, this might need to signal all running processes or be handled differently.
    print(f"--- [Disconnect Event] Triggered! Setting main stop_event. Event data: {e} ---", flush=True)
    if not app_state.stop_event.is_set():  # Still uses the old singleton event
        app_state.stop_event.set()
    print("[Disconnect Event] Main stop_event set. atexit handler will perform final cleanup.", flush=True)


# --- New Generic Stop Function ---
def stop_managed_process(process_id: str, page: Optional[ft.Page], app_state: "AppState"):
    """Stops a specific managed process by its ID."""
    print(f"[Stop Managed] Request to stop process ID: '{process_id}'", flush=True)
    process_state = app_state.managed_processes.get(process_id)

    if not process_state:
        print(f"[Stop Managed] Process ID '{process_id}' not found in managed processes.", flush=True)
        if page and process_id == "bot.py":  # Show snackbar only for the main bot?
            # from .utils import show_snackbar; show_snackbar(page, "Bot process not found or already stopped.") # Already imported at top
            show_snackbar(page, "Bot process not found or already stopped.")
        # If it's the main bot, ensure button state is correct
        if process_id == "bot.py":
            update_buttons_state(page, app_state, is_running=False)
        return

    # Signal the specific stop event for this process
    if not process_state.stop_event.is_set():
        print(f"[Stop Managed] Setting stop_event for ID: '{process_id}'", flush=True)
        process_state.stop_event.set()

    # Attempt termination
    _terminate_process_gracefully(process_id, process_state.process_handle, process_state.pid)

    # Update state in AppState dictionary
    process_state.status = "stopped"
    process_state.process_handle = None  # Clear handle
    process_state.pid = None  # Clear PID
    # Optionally remove the entry from the dictionary entirely?
    # del app_state.managed_processes[process_id]
    print(f"[Stop Managed] Marked process ID '{process_id}' as stopped in AppState.")

    # Update UI (specifically for the main bot for now)
    if process_id == "bot.py":
        # If the process being stopped is the main bot, update the console button
        update_buttons_state(page, app_state, is_running=False)
        # Also clear the old singleton state for compatibility
        app_state.clear_process()  # This now also updates the dict entry

    # TODO: Add UI update logic for other processes if a management view exists


# --- Adapted Old Stop Function (Calls the new generic one) ---
def stop_bot_process(page: Optional[ft.Page], app_state: "AppState"):
    """(Called by Button) Stops the main bot.py process by calling stop_managed_process."""
    stop_managed_process("bot.py", page, app_state)


# --- Parameterized Reader Thread ---
def read_process_output(
    app_state: "AppState",  # Still pass app_state for global checks? Or remove? Let's keep for now.
    process_handle: Optional[subprocess.Popen] = None,
    output_queue: Optional[queue.Queue] = None,
    stop_event: Optional[threading.Event] = None,
    process_id: str = "bot.py",  # ID for logging
):
    """
    Background thread function to read raw output from a process and put it into a queue.
    Defaults to using AppState singletons if specific handles/queues/events aren't provided.
    """
    # Use provided arguments or default to AppState singletons
    proc_handle = process_handle if process_handle is not None else app_state.bot_process
    proc_queue = output_queue if output_queue is not None else app_state.output_queue
    proc_stop_event = stop_event if stop_event is not None else app_state.stop_event

    if not proc_handle or not proc_handle.stdout:
        if not proc_stop_event.is_set():
            print(f"[Reader Thread - {process_id}] Error: Process or stdout not available at start.", flush=True)
        return

    print(f"[Reader Thread - {process_id}] Started.", flush=True)
    try:
        # Popen with text=True and encoding=... handles the decoding.
        # line should already be a string.
        for line in iter(proc_handle.stdout.readline, ""):
            if proc_stop_event.is_set():
                print(f"[Reader Thread - {process_id}] Stop event detected, exiting.", flush=True)
                break
            if line:
                # Directly put the stripped string into the queue.
                proc_queue.put(line.strip())
            else:
                break  # End of stream
    except ValueError:
        # This might happen if the process closes stdout abruptly while reading.
        if not proc_stop_event.is_set():
            print(f"[Reader Thread - {process_id}] ValueError likely due to closed stdout.", flush=True)
    except Exception as e:
        # Catch other potential reading errors.
        if not proc_stop_event.is_set():
            print(f"[Reader Thread - {process_id}] Error reading output: {e}", flush=True)
            # Optional: Log traceback for detailed debugging
            # import traceback
            # traceback.print_exc()
    finally:
        # Signal the natural end of the stream to the processor loop.
        if not proc_stop_event.is_set():
            try:
                # Use put_nowait or handle potential Full exception if queue is bounded
                proc_queue.put(None)
            except Exception as q_err:
                print(f"[Reader Thread - {process_id}] Error putting None signal: {q_err}", flush=True)
        print(f"[Reader Thread - {process_id}] Finished.", flush=True)


# --- Parameterized Processor Loop ---
async def output_processor_loop(
    page: Optional[ft.Page],
    app_state: "AppState",  # Pass AppState for PID checks and potentially global state access
    process_id: str = "bot.py",  # ID to identify the process and its state
    # Defaults use AppState singletons for backward compatibility with bot.py
    output_queue: Optional[queue.Queue] = None,
    stop_event: Optional[threading.Event] = None,
    target_list_view: Optional[ft.ListView] = None,
):
    """
    Processes a specific output queue and updates the UI until stop_event is set.
    Defaults to using AppState singletons if specific queue/event/view aren't provided.
    """
    print(f"[Processor Loop - {process_id}] Started.", flush=True)
    proc_queue = output_queue if output_queue is not None else app_state.output_queue
    proc_stop_event = stop_event if stop_event is not None else app_state.stop_event
    output_lv = target_list_view if target_list_view is not None else app_state.output_list_view

    # from .utils import update_page_safe # Moved to top

    while not proc_stop_event.is_set():
        lines_to_add = []
        process_ended_signal_received = False

        try:
            # Process all available lines in the queue currently.
            while not proc_queue.empty():
                # raw_line should be a string from the reader thread.
                raw_line = proc_queue.get_nowait()
                if raw_line is None:
                    process_ended_signal_received = True
                    print(f"[Processor Loop - {process_id}] Process ended signal received from reader.", flush=True)
                    lines_to_add.append(ft.Text(f"--- Process '{process_id}' Finished --- ", italic=True))
                    break # Exit inner loop once None is received
                else:
                    # Directly parse the string. Assume it's correctly decoded.
                    try:
                        spans = parse_log_line_to_spans(raw_line)
                        lines_to_add.append(ft.Text(spans=spans, selectable=True, size=12))
                    except Exception as parse_err:
                        # If parsing fails (e.g., complex ANSI), display raw line
                        print(f"[Processor Loop - {process_id}] Error parsing line with color codes: {parse_err}. Line: {repr(raw_line)}", flush=True)
                        lines_to_add.append(ft.Text(raw_line, selectable=True, size=12, color=ft.colors.ERROR))

        except queue.Empty:
            # Queue is empty, wait for more lines.
            pass
        except Exception as loop_err:
            # Catch unexpected errors in the loop itself
            print(f"[Processor Loop - {process_id}] Unexpected error in processing loop: {loop_err}", flush=True)
            traceback.print_exc() # Print stack trace for debugging
            # Consider adding a generic error message to the UI as well
            # lines_to_add.append(ft.Text("--- Internal Processing Error ---", color=ft.colors.RED, italic=True))


        if lines_to_add:
            if proc_stop_event.is_set(): # Double-check stop event before UI update
                print(f"[Processor Loop - {process_id}] Stop event set before UI update, discarding lines.")
                break

            if output_lv:
                # --- UI Update Logic (Simplified slightly for clarity) ---
                # Determine if manual viewing mode is active for the main bot console
                is_manual_viewing_active = (
                    process_id == "bot.py" and
                    hasattr(app_state, "manual_viewing") and app_state.manual_viewing and
                    not getattr(output_lv, "auto_scroll", True)
                )

                current_first_visible = 0
                if is_manual_viewing_active and hasattr(output_lv, "first_visible"):
                    current_first_visible = output_lv.first_visible or 0

                # Add new lines
                output_lv.controls.extend(lines_to_add)

                # Limit history size
                removal_count = 0
                max_lines = 1000 # Configurable?
                while len(output_lv.controls) > max_lines:
                    output_lv.controls.pop(0)
                    removal_count += 1

                # Adjust scroll position if in manual viewing and lines were removed
                if is_manual_viewing_active and removal_count > 0:
                    adjusted_first_visible = max(0, current_first_visible - removal_count)
                    # Check if scroll position actually needs setting
                    # Setting it unnecessarily might cause flicker?
                    if output_lv.first_visible != adjusted_first_visible:
                        output_lv.scroll_to(index=adjusted_first_visible)
                        # print(f"[Processor Loop - {process_id}] Manual scroll adjusted: {current_first_visible} -> {adjusted_first_visible}")
                # else: Auto-scroll handles it, or no lines removed.

                # Update the page if the list view is visible
                if output_lv.visible and page:
                    try:
                        await update_page_safe(page)
                    except Exception as update_err:
                        # Log error but continue if page update fails
                        print(f"[Processor Loop - {process_id}] Error updating page: {update_err}", flush=True)
                        # traceback.print_exc() # Optional detailed logging
            else:
                 print(f"[Processor Loop - {process_id}] Warning: target_list_view is None, cannot display output.")

        if process_ended_signal_received:
            print(
                f"[Processor Loop - {process_id}] Process ended naturally. Setting stop event and cleaning up.",
                flush=True,
            )
            if not proc_stop_event.is_set():
                proc_stop_event.set()
            # Update the specific process state in the dictionary
            proc_state = app_state.managed_processes.get(process_id)
            if proc_state:
                proc_state.status = "stopped"
                proc_state.process_handle = None
                proc_state.pid = None
            # If it's the main bot, also update the old state and buttons
            if process_id == "bot.py":
                app_state.clear_process()  # Clears old state and marks new as stopped
                update_buttons_state(page, app_state, is_running=False)
            break

        # Check if the specific process died unexpectedly using its PID from managed_processes
        current_proc_state = app_state.managed_processes.get(process_id)
        current_pid = current_proc_state.pid if current_proc_state else None

        # Check PID existence only if we expect it to be running
        if current_pid is not None and current_proc_state and current_proc_state.status == "running":
             if not psutil.pid_exists(current_pid) and not proc_stop_event.is_set():
                print(
                    f"[Processor Loop - {process_id}] Process PID {current_pid} ended unexpectedly. Setting stop event.",
                    flush=True,
                )
                proc_stop_event.set()
                if current_proc_state:  # Update state
                    current_proc_state.status = "stopped"
                    current_proc_state.process_handle = None
                    current_proc_state.pid = None
                # Add message to its specific output view
                if output_lv:
                    output_lv.controls.append(ft.Text(f"--- Process '{process_id}' Ended Unexpectedly ---", italic=True))
                    if page and output_lv.visible:
                        try:
                            await update_page_safe(page)
                        except Exception:
                            pass # Ignore update error here
                # If it's the main bot, update buttons and old state
                if process_id == "bot.py":
                    app_state.clear_process()
                    update_buttons_state(page, app_state, is_running=False)
                break # Exit loop after detecting unexpected termination

        # Wait before checking the queue again
        try:
            await asyncio.sleep(0.2) # Polling interval
        except asyncio.CancelledError:
            print(f"[Processor Loop - {process_id}] Cancelled during sleep.", flush=True)
            if not proc_stop_event.is_set():
                proc_stop_event.set()
            break # Exit loop if cancelled

    print(f"[Processor Loop - {process_id}] Exited.", flush=True)


# --- New Generic Start Function ---
def start_managed_process(
    script_path: str,
    display_name: str,
    page: ft.Page,
    app_state: "AppState",
    # target_list_view: Optional[ft.ListView] = None # Removed parameter
) -> Tuple[bool, Optional[str]]:
    """
    Starts a managed background process, creates its state, and starts reader/processor.
    Returns (success: bool, message: Optional[str])
    """
    # from .utils import show_snackbar # Dynamic import - Already imported at top
    from .state import ManagedProcessState  # Dynamic import

    process_id = script_path  # Use script path as ID for now, ensure uniqueness later if needed

    # Prevent duplicate starts if ID already exists and is running
    existing_state = app_state.managed_processes.get(process_id)
    if (
        existing_state
        and existing_state.status == "running"
        and existing_state.pid
        and psutil.pid_exists(existing_state.pid)
    ):
        msg = f"Process '{display_name}' (ID: {process_id}) is already running."
        print(f"[Start Managed] {msg}", flush=True)
        # show_snackbar(page, msg) # Maybe too noisy?
        return False, msg

    full_path = os.path.join(app_state.script_dir, script_path)
    if not os.path.exists(full_path):
        msg = f"Error: Script file not found {script_path}"
        print(f"[Start Managed] {msg}", flush=True)
        show_snackbar(page, msg, error=True)
        return False, msg

    print(f"[Start Managed] Preparing to start NEW process: {display_name} ({script_path})", flush=True)

    # Create NEW state object for this process with its OWN queue and event
    # UNLESS it's bot.py, in which case we still use the old singletons for now
    is_main_bot = script_path == "bot.py"
    new_queue = app_state.output_queue if is_main_bot else queue.Queue()
    new_event = app_state.stop_event if is_main_bot else threading.Event()

    new_process_state = ManagedProcessState(
        process_id=process_id,
        script_path=script_path,
        display_name=display_name,
        output_queue=new_queue,
        stop_event=new_event,
        status="starting",
    )
    # Add to managed processes *before* starting
    app_state.managed_processes[process_id] = new_process_state

    # --- Create and store ListView if not main bot --- #
    output_lv: Optional[ft.ListView] = None
    if is_main_bot:
        output_lv = app_state.output_list_view  # Use the main console view
    else:
        # Create and store a new ListView for this specific process
        output_lv = ft.ListView(expand=True, spacing=2, padding=5, auto_scroll=True)  # 始终默认开启自动滚动
        new_process_state.output_list_view = output_lv

    # Add starting message to the determined ListView
    if output_lv:
        output_lv.controls.append(ft.Text(f"--- Starting {display_name} --- ", italic=True))
    else:  # Should not happen if is_main_bot or created above
        print(f"[Start Managed - {process_id}] Error: Could not determine target ListView.")

    try:
        print(f"[Start Managed - {process_id}] Starting subprocess: {full_path}", flush=True)
        sub_env = os.environ.copy()
        # Set env vars if needed (e.g., for colorization)
        sub_env["LOGURU_COLORIZE"] = "True"
        sub_env["FORCE_COLOR"] = "1"
        sub_env["SIMPLE_OUTPUT"] = "True"
        print(
            f"[Start Managed - {process_id}] Subprocess environment set: COLORIZE={sub_env.get('LOGURU_COLORIZE')}, FORCE_COLOR={sub_env.get('FORCE_COLOR')}, SIMPLE_OUTPUT={sub_env.get('SIMPLE_OUTPUT')}",
            flush=True,
        )

        # --- 修改启动命令 ---
        cmd_list = []
        executable_path = ""  # 用于日志记录

        # 检查是否有用户自定义的 Python 路径
        if app_state.python_path and os.path.exists(app_state.python_path):
            # 使用用户指定的 Python 解释器
            cmd_list = [app_state.python_path, "-u", full_path]
            executable_path = app_state.python_path
            print(f"[Start Managed - {process_id}] 使用用户指定的 Python: {executable_path}")
        elif getattr(sys, "frozen", False):
            # 打包后运行
            executable_dir = os.path.dirname(sys.executable)

            # 修改逻辑：这次我们直接指定 _internal 目录下的 Python 解释器
            # 而不是尝试其他选项
            try:
                # _internal 目录是 PyInstaller 默认放置 Python 解释器的位置
                internal_dir = os.path.join(executable_dir, "_internal")

                if os.path.exists(internal_dir):
                    print(f"[Start Managed - {process_id}] 找到 _internal 目录: {internal_dir}")

                    # 在 _internal 目录中查找 python.exe
                    python_exe = None
                    python_paths = []

                    # 首先尝试直接查找
                    direct_python = os.path.join(internal_dir, "python.exe")
                    if os.path.exists(direct_python):
                        python_exe = direct_python
                        python_paths.append(direct_python)

                    # 如果没找到，进行递归搜索
                    if not python_exe:
                        for root, _, files in os.walk(internal_dir):
                            if "python.exe" in files:
                                path = os.path.join(root, "python.exe")
                                python_paths.append(path)
                                if not python_exe:  # 只取第一个找到的
                                    python_exe = path

                    # 记录所有找到的路径
                    if python_paths:
                        print(f"[Start Managed - {process_id}] 在 _internal 中找到的所有 Python.exe: {python_paths}")

                    if python_exe:
                        # 找到 Python 解释器，使用它来运行脚本
                        cmd_list = [python_exe, "-u", full_path]
                        executable_path = python_exe
                        print(f"[Start Managed - {process_id}] 使用打包内部的 Python: {executable_path}")
                    else:
                        # 如果找不到，只能使用脚本文件直接执行
                        print(f"[Start Managed - {process_id}] 无法在 _internal 目录中找到 python.exe")
                        cmd_list = [full_path]
                        executable_path = full_path
                        print(f"[Start Managed - {process_id}] 直接执行脚本: {executable_path}")
                else:
                    # _internal 目录不存在，尝试直接执行脚本
                    print(f"[Start Managed - {process_id}] _internal 目录不存在: {internal_dir}")
                    cmd_list = [full_path]
                    executable_path = full_path
                    print(f"[Start Managed - {process_id}] 直接执行脚本: {executable_path}")
            except Exception as path_err:
                print(f"[Start Managed - {process_id}] 查找 Python 路径时出错: {path_err}")
                # 如果出现异常，尝试直接执行脚本
                cmd_list = [full_path]
                executable_path = full_path
                print(f"[Start Managed - {process_id}] 出错回退：直接执行脚本 {executable_path}")
        else:
            # 源码运行，使用当前的 Python 解释器
            cmd_list = [sys.executable, "-u", full_path]
            executable_path = sys.executable
            print(f"[Start Managed - {process_id}] 源码模式：使用当前 Python ({executable_path})")

        print(f"[Start Managed - {process_id}] 最终命令列表: {cmd_list}")

        # --- 获取用户选择的编码 --- #
        # 从 AppState 中的 gui_config 读取设置，提供默认值 utf-8
        selected_encoding = app_state.gui_config.get("subprocess_encoding", "utf-8")
        print(f"[Start Managed - {process_id}] 使用编码 '{selected_encoding}' 启动子进程 (来自 GUI 设置)")

        process = subprocess.Popen(
            cmd_list,  # 使用构建好的命令列表
            cwd=app_state.script_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=selected_encoding, 
            errors="replace", # 替换无法解码的字符，避免程序崩溃
            bufsize=1, # 行缓冲
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            env=sub_env,
        )

        # Update the state with handle and PID
        new_process_state.process_handle = process
        new_process_state.pid = process.pid
        new_process_state.status = "running"
        print(f"[Start Managed - {process_id}] Subprocess started. PID: {process.pid}", flush=True)

        # If it's the main bot, also update the old state vars for compatibility
        if is_main_bot:
            app_state.bot_process = process
            app_state.bot_pid = process.pid
            update_buttons_state(page, app_state, is_running=True)

        # Start the PARAMETERIZED reader thread
        output_thread = threading.Thread(
            target=read_process_output,
            args=(app_state, process, new_queue, new_event, process_id),  # Pass specific objects
            daemon=True,
        )
        output_thread.start()
        print(f"[Start Managed - {process_id}] Output reader thread started.", flush=True)

        # Start the PARAMETERIZED processor loop task
        # Pass the determined output_lv (either main console or the new one)
        page.run_task(output_processor_loop, page, app_state, process_id, new_queue, new_event, output_lv)
        print(f"[Start Managed - {process_id}] Output processor loop scheduled.", flush=True)

        return True, f"Process '{display_name}' started successfully."

    except Exception as e:
        print(f"[Start Managed - {process_id}] Error during startup:", flush=True)
        traceback.print_exc()
        # Clean up state if startup failed
        new_process_state.status = "error"
        new_process_state.process_handle = None
        new_process_state.pid = None
        if process_id in app_state.managed_processes:  # Might be redundant check
            app_state.managed_processes[process_id].status = "error"

        if is_main_bot:  # Update UI/state for main bot failure
            app_state.clear_process()
            update_buttons_state(page, app_state, is_running=False)

        error_message = str(e) if str(e) else repr(e)
        show_snackbar(page, f"Error running {script_path}: {error_message}", error=True)
        return False, f"Error starting process '{display_name}': {error_message}"


# --- Adapted Start Bot Function (Calls new generic start) ---

def start_bot_and_show_console(page: ft.Page, app_state: "AppState"):
    """
    Starts the main bot process (using the path from app_state.bot_script_path)
    and navigates to the console view.
    Uses the new start_managed_process internally.
    """
    print("[Start Console] Attempting to start main bot process and show console...")

    # Use the configurable bot script path from AppState
    bot_script = app_state.bot_script_path
    print(f"[Start Console] Using bot script path: {bot_script}")

    # --- Call the generic start function --- #
    # Pass None for target_list_view, as the main console view uses app_state.output_list_view
    success, error_message = start_managed_process(
        script_path=bot_script,
        display_name="MaiCore",  # Display name for the main bot
        page=page,
        app_state=app_state,
        # target_list_view=None # Removed parameter
    )

    if success:
        print("[Start Console] start_managed_process reported success.")
        # Navigate to console view
        page.go("/console")
        # Button state is updated within start_managed_process via set_process
        # update_buttons_state(page, app_state, is_running=True) # No longer needed here
    else:
        print(f"[Start Console] start_managed_process failed: {error_message}")
        # Ensure button state reflects failure
        update_buttons_state(page, app_state, is_running=False)
        # Show error message (snackbar shown inside start_managed_process)
        # if page and error_message:
        #    show_snackbar(page, f"启动失败: {error_message}", bgcolor=ft.colors.RED_200)


# --- Application Exit Cleanup (No Change Needed) ---
# cleanup_on_exit remains the same, registered with atexit in launcher
