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
        print(f"[Update Buttons] 状态改变，触发页面更新。is_running={is_running}")
        print(f"[Update Buttons] 页面更新{page}")
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


# --- 通用停止函数 ---
def stop_managed_process(process_id: str, page: Optional[ft.Page], app_state: "AppState"):
    """停止指定ID的管理进程"""
    print(f"[停止管理] 请求停止进程: '{process_id}'", flush=True)
    process_state = app_state.managed_processes.get(process_id)

    # 检查进程状态是否存在
    if not process_state:
        print(f"[停止管理] 未找到进程 '{process_id}'", flush=True)
        if page and process_id == "mmc":
            show_snackbar(page, "机器人进程未运行")
        if process_id == "mmc":
            update_buttons_state(page, app_state, is_running=False)
        return

    # 发送停止信号
    if not process_state.stop_event.is_set():
        print(f"[停止管理] 设置停止事件: '{process_id}'", flush=True)
        process_state.stop_event.set()

    # 尝试优雅终止进程
    _terminate_process_gracefully(process_id, process_state.process_handle, process_state.pid)

    # 更新应用状态
    process_state.status = "stopped"
    process_state.process_handle = None
    process_state.pid = None
    print(f"[停止管理] 进程 '{process_id}' 已标记为停止")
    
    # 重要：清除stop_event，以便下次启动
    process_state.stop_event.clear()
    print(f"[停止管理] 进程 '{process_id}' 的stop_event已清除")

    # 如果是主机器人进程则更新UI
    if process_id == "mmc":
        update_buttons_state(page, app_state, is_running=False)
        app_state.clear_process()  # 清理旧状态保持兼容
        app_state.stop_event.clear()  # 确保主停止事件也被清除
        print(f"[停止管理] 主stop_event已清除")

    # TODO: Add UI update logic for other processes if a management view exists


# --- Adapted Old Stop Function (Calls the new generic one) ---
def stop_bot_process(page: Optional[ft.Page], app_state: "AppState"):
    """(Called by Button) Stops the main bot.py process by calling stop_managed_process."""
    stop_managed_process("mmc", page, app_state)


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
                # [调试] 输出从 bot.py 读取到的原始内容
                print(f"[调试] 从 {process_id} 读取的原始内容: {repr(line)}", flush=True)
                
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
    output_queue: Optional[queue.Queue] = None,
    stop_event: Optional[threading.Event] = None,
    target_list_view: Optional[ft.ListView] = None,
):
    """
    处理特定的输出队列并更新UI，直到stop_event被触发。
    如果没有提供特定的队列/事件/视图参数，则默认使用AppState中的单例对象。
    """
    print(f"[Processor Loop - {process_id}] Started.", flush=True)
    proc_queue = output_queue if output_queue is not None else app_state.output_queue
    proc_stop_event = stop_event if stop_event is not None else app_state.stop_event
    output_lv = target_list_view 

    # 设置循环退出标志
    loop_exited_normally = False

    try:
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
                        if process_id == "bot.py":
                            lines_to_add.append(ft.Text("--- Bot 进程已结束，可重新启动 ---", italic=True))
                        else:
                            lines_to_add.append(ft.Text(f"--- Process '{process_id}' Finished --- ", italic=True))
                        break # Exit inner loop once None is received
                    else:
                        # [调试] 处理前的队列内容
                        # print(f"[调试] 准备处理的队列内容: {repr(raw_line)}", flush=True)
                        
                        # Directly parse the string. Assume it's correctly decoded.
                        try:
                            spans = parse_log_line_to_spans(raw_line)
                            text_obj = ft.Text(spans=spans, selectable=True, size=12)
                            lines_to_add.append(text_obj)
                            
                            # [调试] 显示处理后要添加到控制台的内容
                            # 提取并显示spans中的文本预览
                            span_text_preview = ""
                            if spans:
                                # 尝试从spans中提取文本进行预览
                                try:
                                    span_text_preview = "".join([span.text for span in spans if hasattr(span, 'text') and span.text])
                                    if len(span_text_preview) > 100:
                                        span_text_preview = span_text_preview[:97] + "..."
                                except Exception as e:
                                    span_text_preview = f"(无法提取文本: {e})"
                            
                            print(f"[调试] 添加到控制台的文本: {span_text_preview or '(spans模式，无法提取内容)'}", flush=True)
                            
                        except Exception as parse_err:
                            # If parsing fails (e.g., complex ANSI), display raw line
                            print(f"[Processor Loop - {process_id}] Error parsing line with color codes: {parse_err}. Line: {repr(raw_line)}", flush=True)
                            
                            error_text = ft.Text(raw_line, selectable=True, size=12, color=ft.colors.ERROR)
                            lines_to_add.append(error_text)
                            
                            # [调试] 显示错误情况下添加的内容
                            print(f"[调试] 解析失败，添加原始文本: {raw_line}", flush=True)

            except queue.Empty:
                pass
            except Exception as loop_err:
                print(f"[Processor Loop - {process_id}] Unexpected error in processing loop: {loop_err}", flush=True)
                traceback.print_exc() 

            # print(f"[Processor Loop - {process_id}] 当前lines_to_add: {lines_to_add}")
            if lines_to_add:
                if proc_stop_event.is_set(): # Double-check stop event before UI update
                    print(f"[Processor Loop - {process_id}] Stop event set before UI update, discarding lines.")
                    loop_exited_normally = True
                    break

                if output_lv:
                    # [调试] 显示添加到ListView的行数
                    print(f"[调试] 添加到 ListView 的行数: {len(lines_to_add)}", flush=True)
                    
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
                    print(f"[调试-第1步] 开始添加{len(lines_to_add)}行内容到ListView控件集合", flush=True)
                    output_lv.controls.extend(lines_to_add)
                    
                    print(f"[调试-第1步] 完成添加，当前ListView控件总数: {len(output_lv.controls)}", flush=True)

                    # 限制历史长度
                    max_lines = 1000 # 可配置的最大行数
                    removal_count = 0
                    while len(output_lv.controls) > max_lines:
                        output_lv.controls.pop(0)
                        removal_count += 1


                    if is_manual_viewing_active and removal_count > 0:
                        print(f"[调试-第3步] 手动查看模式 & 有行被移除，当前first_visible={current_first_visible}", flush=True)
                        adjusted_first_visible = max(0, current_first_visible - removal_count)
                        # Check if scroll position actually needs setting
                        # Setting it unnecessarily might cause flicker?
                        if output_lv.first_visible != adjusted_first_visible:
                            print(f"[调试-第3步] 调整滚动位置: {current_first_visible} -> {adjusted_first_visible}", flush=True)
                            output_lv.scroll_to(index=adjusted_first_visible)

                    
                    print(f"[调试-第4步] 开始更新UI界面, ListView可见性: {output_lv.visible}", flush=True)
                    if output_lv.visible and page:
                        print(f"[调试-第4步] 调用update_page_safe更新页面", flush=True)
                        print(f"output_list_view存在: {app_state.output_list_view is not None}")
                        if app_state.output_list_view:
                            print(f"  - 控件数: {len(app_state.output_list_view.controls)}")
                            print(f"  - 可见性: {app_state.output_list_view.visible}")
                            print(f"  - 已添加到页面: {hasattr(app_state.output_list_view, '_Control__page')}")
                        print(page)
                        await update_page_safe(page)
                        print(f"[调试-第4步] 页面更新完成", flush=True)
                    else:
                        print(f"[调试-第4步] 跳过页面更新: ListView不可见或page为None", flush=True)

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
                    proc_state.has_run_before = True  # 标记为已运行过
                # If it's the main bot, also update the old state and buttons
                if process_id == "bot.py":
                    app_state.clear_process()  # Clears old state and marks new as stopped
                    update_buttons_state(page, app_state, is_running=False)
                loop_exited_normally = True
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
                    loop_exited_normally = True
                    break

            # Wait before checking the queue again
            try:
                print(f"[调试-第5步] 等待新内容，休眠0.2秒", flush=True)
                await asyncio.sleep(0.2) # Polling interval
                print(f"[调试-第5步] 休眠结束，准备下一次循环", flush=True)
            except asyncio.CancelledError:
                print(f"[Processor Loop - {process_id}] Cancelled during sleep.", flush=True)
                if not proc_stop_event.is_set():
                    proc_stop_event.set()
                loop_exited_normally = True
                break # Exit loop if cancelled
    finally:
        # 在方法结束时检查是否正常退出，如果不是，则确保设置停止标志
        if not loop_exited_normally and not proc_stop_event.is_set():
            print(f"[Processor Loop - {process_id}] 异常退出循环！强制设置停止标志。", flush=True)
            proc_stop_event.set()
            # 更新进程状态
            current_proc_state = app_state.managed_processes.get(process_id)
            if current_proc_state:
                current_proc_state.status = "stopped"
                current_proc_state.process_handle = None
                current_proc_state.pid = None
            # 如果是主机器人进程，也更新旧状态和按钮
            if process_id == "bot.py":
                app_state.clear_process()
                if page:
                    update_buttons_state(page, app_state, is_running=False)

    print(f"[Processor Loop - {process_id}] 已退出。", flush=True)


# --- New Generic Start Function ---
def start_managed_process(
    script_path: str,
    type: str,
    display_name: str,
    page: ft.Page,
    app_state: "AppState",
) -> Tuple[bool, Optional[str]]:
    """
    启动一个受管理的后台进程，创建其状态并启动读取器/处理器
    Starts a managed background process, creates its state, and starts reader/processor.
    
    返回: (是否成功: 布尔值, 消息: 可选字符串)
    Returns: (success: bool, message: Optional[str])
    """
    from .state import ManagedProcessState  # Dynamic import
    
    process_id = "mmc"

    # 防止重复启动已存在的运行中进程
    existing_state = app_state.managed_processes.get(process_id)
    if (
        existing_state
        and existing_state.status == "running" 
        and existing_state.pid
        and psutil.pid_exists(existing_state.pid)
    ):
        msg = f"进程 '{display_name}' (ID: {process_id}) 已在运行中"
        print(f"[Start Managed] {msg}", flush=True)
        return False, msg

    full_path = os.path.join(app_state.script_dir, script_path)
    if not os.path.exists(full_path):
        msg = f"错误：未找到脚本文件 {script_path}"
        print(f"[启动管理进程] {msg}", flush=True)
        show_snackbar(page, msg, error=True)
        return False, msg

    print(f"[Start Managed] Preparing to start NEW process: {display_name} ({script_path})", flush=True)

    # Create NEW state object for this process with its OWN queue and event
    # UNLESS it's bot.py, in which case we still use the old singletons for now
    if type == "mmc":
        is_main_bot = True
    else:
        is_main_bot = False
    print(f"[Start Managed] is_main_bot={is_main_bot}")
    new_queue = app_state.output_queue if is_main_bot else queue.Queue()
    new_event = app_state.stop_event if is_main_bot else threading.Event()

    # 检查是否之前运行过
    has_run_before = False
    existing_process = app_state.managed_processes.get(process_id)
    if existing_process:
        has_run_before = existing_process.has_run_before

    new_process_state = ManagedProcessState(
        process_id=process_id,
        script_path=script_path,
        display_name=display_name,
        output_queue=new_queue,
        stop_event=new_event,
        status="starting",
        has_run_before=has_run_before  # 保留之前的运行状态
    )
    
    app_state.managed_processes[process_id] = new_process_state


    output_lv: Optional[ft.ListView] = None
    if is_main_bot:
        output_lv = app_state.output_list_view  # Use the main console view
    else:
        # Create and store a new ListView for this specific process
        output_lv = ft.ListView(expand=True, spacing=2, padding=5, auto_scroll=True)  # 始终默认开启自动滚动
        new_process_state.output_list_view = output_lv
    
    # output_lv = app_state.output_list_view

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
        else:
            # 不再尝试使用内部解释器或当前解释器
            error_msg = "未设置有效的 Python 解释器路径。请在设置中指定 Python 解释器路径。"
            print(f"[Start Managed - {process_id}] {error_msg}")
            
            if output_lv and len(output_lv.controls) > 0:
                output_lv.controls.append(ft.Text(f"错误: {error_msg}", color=ft.colors.RED))
                if page:
                    try:
                        output_lv.update()
                    except:
                        pass  # 忽略可能的更新错误
            
            # 显示错误消息
            if page:
                show_snackbar(page, error_msg, error=True)
            
            # 更新状态
            new_process_state.status = "error"
            if is_main_bot:
                app_state.clear_process()
                update_buttons_state(page, app_state, is_running=False)
            
            return False, error_msg

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
        new_process_state.has_run_before = True  # 标记为已运行过
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


        page.run_task(output_processor_loop,
                    page=page,
                    app_state=app_state,
                    process_id=process_id,
                    output_queue=new_queue,
                    stop_event=new_event,
                    target_list_view=output_lv)
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
    启动主机器人进程(使用app_state.bot_script_path中的路径)
    并导航到控制台视图。
    内部使用新的start_managed_process方法。
    """

    bot_script = app_state.bot_script_path
    print(f"[Start Console] Using bot script path: {bot_script}")
    print(f"[Start Console] 调用start_managed_process,bot_script={bot_script}")
    # --- Call the generic start function --- #
    success, error_message = start_managed_process(
        script_path=bot_script,
        type = "mmc",
        display_name="MaiCore",  # Display name for the main bot
        page=page,
        app_state=app_state,
    )

    if success:
        print("[Start Console] start_managed_process reported success.")
        page.go("/console")
    else:
        print(f"[Start Console] start_managed_process failed: {error_message}")
        update_buttons_state(page, app_state, is_running=False)



