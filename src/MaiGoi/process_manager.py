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
import time
from typing import Optional, TYPE_CHECKING, Tuple
from loguru import logger

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
            logger.info("[Update Buttons] Warning: console_action_button content is not Text?")

    if needs_update and page:
        logger.info(f"[Update Buttons] 状态改变，触发页面更新。is_running={is_running}")
        logger.info(f"[Update Buttons] 页面更新{page}")
        page.run_task(update_page_safe, page)


# 通用进程终止辅助函数
def _terminate_process_gracefully(process_id: str, handle: Optional[subprocess.Popen], pid: Optional[int]):
    """尝试优雅终止进程，失败后强制终止"""
    stopped_cleanly = False
    
    if handle and pid:  # 如果有进程句柄和PID
        logger.info(f"[终止] 尝试终止进程 PID: {pid} (ID: {process_id})...")
        if handle.poll() is None:  # 进程仍在运行
            handle.terminate()  # 先尝试优雅终止
            try:
                handle.wait(timeout=1.0)  # 等待1秒
                logger.info(f"[终止] 进程 PID: {pid} 已优雅终止")
                stopped_cleanly = True
            except subprocess.TimeoutExpired:  # 超时后强制终止
                handle.kill()
                logger.info(f"[终止] 强制终止 PID: {pid}")
        else:  # 进程已停止
            stopped_cleanly = True
    
    elif pid:  # 只有PID没有句柄时使用psutil
        logger.info(f"[终止] 无句柄，使用psutil终止 PID: {pid}...")
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
                stopped_cleanly = True
            except psutil.TimeoutExpired:
                proc.kill()
                logger.info(f"[终止] psutil终止 PID {pid}")
        else:
            stopped_cleanly = True  # 进程已不存在
    
    else:  # 无有效句柄或PID
        logger.info(f"[终止] 无法终止进程 '{process_id}': 无句柄或PID")
        stopped_cleanly = True

    return stopped_cleanly


# --- Process Management Functions (Refactored for Multi-Process) --- #


def cleanup_on_exit(app_state: "AppState"):
    """Registered with atexit to ensure ALL managed processes are killed on script exit."""
    logger.info("--- [atexit Cleanup] Running cleanup function ---")
    # Iterate through a copy of the keys to avoid modification issues
    process_ids = list(app_state.managed_processes.keys())
    logger.info(f"[atexit Cleanup] Found managed process IDs: {process_ids}")

    for process_id in process_ids:
        process_state = app_state.managed_processes.get(process_id)
        if process_state and process_state.pid:
            logger.info(f"[atexit Cleanup] Checking PID: {process_state.pid} for ID: {process_id}...")
            try:
                # Use psutil directly as handles might be invalid in atexit
                if psutil.pid_exists(process_state.pid):
                    logger.info(
                        f"[atexit Cleanup] PID {process_state.pid} exists. Attempting termination/kill..."
                    )
                    proc = psutil.Process(process_state.pid)
                    proc.terminate()
                    try:
                        proc.wait(timeout=0.5)
                    except psutil.TimeoutExpired:
                        proc.kill()
                    logger.info(
                        f"[atexit Cleanup] psutil terminate/kill signal sent for PID {process_state.pid}."
                    )
                else:
                    logger.info(f"[atexit Cleanup] PID {process_state.pid} does not exist.")
            except psutil.NoSuchProcess:
                logger.info(f"[atexit Cleanup] psutil.NoSuchProcess error checking PID {process_state.pid}.")
            except Exception as ps_err:
                logger.info(f"[atexit Cleanup] Error cleaning up PID {process_state.pid}: {ps_err}")
        elif process_state:
            logger.info(f"[atexit Cleanup] Process ID '{process_id}' has no PID stored.")
        # else: Process ID might have been removed already

    logger.info("--- [atexit Cleanup] Cleanup function finished ---")


def handle_disconnect(page: Optional[ft.Page], app_state: "AppState", e):
    """Handles UI disconnect. Sets the stop_event for the main bot.py process FOR NOW."""
    # TODO: In a full multi-process model, this might need to signal all running processes or be handled differently.
    logger.info(f"--- [Disconnect Event] Triggered! Setting main stop_event. Event data: {e} ---")
    if not app_state.stop_event.is_set():  # Still uses the old singleton event
        app_state.stop_event.set()
    logger.info("[Disconnect Event] Main stop_event set. atexit handler will perform final cleanup.")


# --- 通用停止函数 ---
def stop_managed_process(process_id: str, page: Optional[ft.Page], app_state: "AppState"):
    """停止指定ID的管理进程"""
    logger.info(f"[停止管理] 请求停止进程: '{process_id}'")
    process_state = app_state.managed_processes.get(process_id)

    # 检查进程状态是否存在
    if not process_state:
        logger.info(f"[停止管理] 未找到进程 '{process_id}'")
        if page and process_id == "mmc":
            show_snackbar(page, "机器人进程未运行")
        if process_id == "mmc":
            update_buttons_state(page, app_state, is_running=False)
        return

    # 发送停止信号
    if not process_state.stop_event.is_set():
        logger.info(f"[停止管理] 设置停止事件: '{process_id}' (脚本: {process_state.script_path})")
        process_state.stop_event.set()

    # 尝试优雅终止进程
    _terminate_process_gracefully(process_id, process_state.process_handle, process_state.pid)

    # 更新应用状态
    process_state.status = "stopped"
    process_state.process_handle = None
    process_state.pid = None
    logger.info(f"[停止管理] 进程 '{process_id}' 已标记为停止")
    
    # 重要：清除stop_event，以便下次启动
    process_state.stop_event.clear()
    logger.info(f"[停止管理] 进程 '{process_id}' 的stop_event已清除")

    # 如果是主机器人进程则更新UI
    if process_id == "mmc":
        update_buttons_state(page, app_state, is_running=False)
        app_state.clear_process()  # 清理旧状态保持兼容
        app_state.stop_event.clear()  # 确保主停止事件也被清除
        logger.info(f"[停止管理] 主stop_event已清除")
        
        # 清空命令行显示
        if app_state.output_list_view:
            logger.info(f"[停止管理] 清空MMC命令行显示")
            time.sleep(0.5)
            app_state.output_list_view.controls.clear()
            app_state.output_list_view.controls.append(ft.Text("--- Bot 进程已停止，命令行已清空 ---", italic=True))
            if page:
                page.update()

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
            logger.info(f"[Reader Thread - {process_id}] Error: Process or stdout not available at start.")
        return

    logger.info(f"[Reader Thread - {process_id}] Started.")
    try:
        for line in iter(proc_handle.stdout.readline, ""):
            if proc_stop_event.is_set():
                # logger.info(f"[Reader Thread - {process_id}] Stop event detected, exiting.")
                break
            if line:
                proc_queue.put(line.strip())
            else:
                break  # End of stream
    except ValueError:
        # This might happen if the process closes stdout abruptly while reading.
        if not proc_stop_event.is_set():
            logger.info(f"[Reader Thread - {process_id}] ValueError likely due to closed stdout.")
    except Exception as e:
        # Catch other potential reading errors.
        if not proc_stop_event.is_set():
            logger.info(f"[Reader Thread - {process_id}] Error reading output: {e}")
    finally:
        # Signal the natural end of the stream to the processor loop.
        if not proc_stop_event.is_set():
            try:
                # Use put_nowait or handle potential Full exception if queue is bounded
                proc_queue.put(None)
            except Exception as q_err:
                logger.info(f"[Reader Thread - {process_id}] Error putting None signal: {q_err}")
        logger.info(f"[Reader Thread - {process_id}] Finished.")


# --- Parameterized Processor Loop ---
async def output_processor_loop(
    page: Optional[ft.Page],
    app_state: "AppState",  # Pass AppState for PID checks and potentially global state access
    process_id: str = "bot.py",  # ID to identify the process and its state
    output_queue: Optional[queue.Queue] = None,
    stop_event: Optional[threading.Event] = None,
    target_list_view: Optional[ft.ListView] = None,
):
    logger.info(f"[Processor Loop - {process_id}] Started.")
    proc_queue = output_queue if output_queue is not None else app_state.output_queue
    proc_stop_event = stop_event if stop_event is not None else app_state.stop_event
    output_lv = target_list_view 
    
    # 检查是否为适配器进程
    is_adapter = process_id.startswith("adapter_")
    
    # 消息批量更新参数
    message_batch = []  # 消息缓冲区
    batch_update_interval = 0.5  # 批量更新间隔，单位秒
    last_update_time = time.time()  # 上次更新时间
    max_batch_size = 20  # 最大批次大小，超过此值将立即更新

    # --- 新增监控变量 ---
    last_metrics_log_time = time.time()
    metrics_log_interval = 5 # 每5秒记录一次聚合指标


    while not proc_stop_event.is_set():
        message_batch = []  # 消息缓冲区
        
        
        loop_start_time = time.monotonic() # 记录循环开始时间

        process_ended_signal_received = False
        current_time = time.time()
        time_since_last_update = current_time - last_update_time
        
        # 持续从队列获取消息，直到队列为空或达到最大批次大小
        queue_empty = False
        processed_in_batch = 0 # 本轮批处理的消息数
        
        batch_collection_start_time = time.monotonic()
        while len(message_batch) < max_batch_size and not queue_empty and not proc_stop_event.is_set():
            try:
                raw_line = proc_queue.get_nowait()
                processed_in_batch +=1
                if raw_line is None:
                    process_ended_signal_received = True
                    logger.info(f"[Processor Loop - {process_id}] Process ended signal received from reader.")
                    if process_id == "mmc": # <--- 修改: "bot.py" -> "mmc"
                        message_batch.append(ft.Text("--- Bot 进程已结束，可重新启动 ---", italic=True))
                    else:
                        message_batch.append(ft.Text(f"--- Process '{process_id}' 已结束 --- ", italic=True))
                    break
                else:
                    spans = parse_log_line_to_spans(raw_line)
                    text_obj = ft.Text(spans=spans, selectable=True, size=12)
                    message_batch.append(text_obj)
                    
                    span_text_preview = ""
                    if spans:
                        # 尝试从spans中提取文本进行预览
                        try:
                            span_text_preview = "".join([span.text for span in spans if hasattr(span, 'text') and span.text])
                            if len(span_text_preview) > 100:
                                span_text_preview = span_text_preview[:97] + "..."
                        except Exception as e:
                            span_text_preview = f"(无法提取文本: {e})"
                    
                    # logger.info(f"[调试] 添加到控制台的文本: {span_text_preview or '(spans模式，无法提取内容)'}")
            except queue.Empty:
                queue_empty = True
        batch_collection_duration = time.monotonic() - batch_collection_start_time
        
        # 判断是否需要更新UI：
        # 1. 缓冲区有消息且已经到了更新间隔
        # 2. 缓冲区有消息且数量达到了最大批次大小
        # 3. 收到了进程结束信号
        should_update = (
            (len(message_batch) > 0 and time_since_last_update >= batch_update_interval) or
            len(message_batch) >= max_batch_size or
            process_ended_signal_received
        )
        
        ui_update_duration = 0 # 初始化，确保在不更新UI的循环中也有定义
        if should_update and message_batch and output_lv and not proc_stop_event.is_set():
            ui_update_start_time = time.monotonic()
            # --- UI Update Logic ---
            # 确定是否在手动查看模式
            is_manual_viewing_active = (
                process_id == "mmc" and # <--- 修改: "bot.py" -> "mmc"
                hasattr(app_state, "manual_viewing") and app_state.manual_viewing and
                not getattr(output_lv, "auto_scroll", True)
            )

            current_first_visible = 0
            if is_manual_viewing_active and hasattr(output_lv, "first_visible"):
                current_first_visible = output_lv.first_visible or 0

            # 限制历史长度并添加新消息
            max_lines = 800  # 可配置的最大行数
            current_len = len(output_lv.controls)
            num_new_lines = len(message_batch)
            
            lines_to_remove_count = 0
            if current_len + num_new_lines > max_lines:
                lines_to_remove_count = (current_len + num_new_lines) - max_lines
                if lines_to_remove_count > current_len: # Cannot remove more than what exists
                    lines_to_remove_count = current_len
                
            if lines_to_remove_count > 0:
                trim_start_time = time.monotonic()
                del output_lv.controls[0:lines_to_remove_count]
                trim_duration = time.monotonic() - trim_start_time
                logger.info(f"[Processor Metrics - {process_id}] Trimmed: {lines_to_remove_count} old lines in {trim_duration:.4f}s. Current controls: {len(output_lv.controls)}")

            # 批量添加所有新消息
            add_controls_start_time = time.monotonic()
            output_lv.controls.extend(message_batch)
            add_controls_duration = time.monotonic() - add_controls_start_time
            logger.info(f"[Processor Metrics - {process_id}] Added: {num_new_lines} new lines in {add_controls_duration:.4f}s. Total controls: {len(output_lv.controls)}")
            

            if is_manual_viewing_active and lines_to_remove_count > 0:
                adjusted_first_visible = max(0, current_first_visible - lines_to_remove_count)
                if output_lv.first_visible != adjusted_first_visible:
                    output_lv.scroll_to(index=adjusted_first_visible, animate=False) # No animation for bg adjustment
                    logger.info(f"[Processor Metrics - {process_id}] Manual view: Adjusted scroll from {current_first_visible} to {adjusted_first_visible} due to trimming.")
    
            
            page_update_call_duration = 0
            # 更新UI（如果可见）
            if output_lv.visible and page:
                page_update_start = time.monotonic()
                await update_page_safe(page)
                page_update_call_duration = time.monotonic() - page_update_start
                logger.info(f"[Processor Metrics - {process_id}] Called page.update(), duration: {page_update_call_duration:.4f}s (approx)")
            
            # 重置批处理变量
            message_batch = []
            last_update_time = time.time()
            ui_update_duration = time.monotonic() - ui_update_start_time
        
        # 处理进程结束信号
        if process_ended_signal_received:
            if not proc_stop_event.is_set():
                proc_stop_event.set()
                
            # 更新进程状态
            proc_state = app_state.managed_processes.get(process_id)
            if proc_state:
                proc_state.status = "stopped"
                proc_state.process_handle = None
                proc_state.pid = None
                proc_state.has_run_before = True  # 标记为已运行过
                
                # 如果是适配器进程，更新适配器管理界面
                if is_adapter and page:
                    page.run_task(lambda: update_ui_after_adapter_stop(page, app_state))
                
            # 如果是主机器人进程，更新旧状态和按钮
            if process_id == "mmc": # <--- 修改: "bot.py" -> "mmc"
                app_state.clear_process()  # Clears old state and marks new as stopped
                update_buttons_state(page, app_state, is_running=False)
            break

        # 检查进程是否意外终止
        current_proc_state = app_state.managed_processes.get(process_id)
        current_pid = current_proc_state.pid if current_proc_state else None

        # 只有当我们期望进程在运行时才检查PID存在性
        if current_pid is not None and current_proc_state and current_proc_state.status == "running":
            if not psutil.pid_exists(current_pid) and not proc_stop_event.is_set():
                logger.info(
                    f"[Processor Loop - {process_id}] Process PID {current_pid} ended unexpectedly. Setting stop event.",
                    flush=True,
                )
                proc_stop_event.set()
                if current_proc_state:  # Update state
                    current_proc_state.status = "stopped"
                    current_proc_state.process_handle = None
                    current_proc_state.pid = None
                # 添加消息到特定输出视图
                if output_lv:
                    output_lv.controls.append(ft.Text(f"--- Process '{process_id}' Ended Unexpectedly ---", italic=True))
                    if page and output_lv.visible:
                        try:
                            await update_page_safe(page)
                        except Exception:
                            pass # Ignore update error here
                # 如果是主机器人进程，更新按钮和旧状态
                if process_id == "mmc": # <--- 修改: "bot.py" -> "mmc"
                    app_state.clear_process()
                    update_buttons_state(page, app_state, is_running=False)
                break # 检测到意外终止后退出循环
        
        loop_duration = time.monotonic() - loop_start_time

        # --- 定期记录聚合指标 ---
        if time.time() - last_metrics_log_time >= metrics_log_interval:
            queue_size = -1 # Default if queue is None or qsize fails
            if proc_queue: # 检查队列是否存在
                try:
                    queue_size = proc_queue.qsize()
                except NotImplementedError: # 一些平台/队列类型可能不支持qsize
                    queue_size = -2 # 表示不支持
            
            active_threads = threading.active_count()
            memory_info = psutil.Process(os.getpid()).memory_info()
            current_lv_controls_count = len(output_lv.controls) if output_lv else 'N/A'
            logger.info(f"[Processor Metrics - {process_id}] Interval Log: QueueSize={queue_size}, BatchCollectTime={batch_collection_duration:.4f}s, LastUIUpdateBlock={ui_update_duration:.4f}s, LoopTime={loop_duration:.4f}s, ActiveThreads={active_threads}, MemRSS={memory_info.rss / 1024**2:.2f}MB, ListViewControls={current_lv_controls_count}")
            last_metrics_log_time = time.time()


        # 如果队列为空且没有消息要处理，等待一小段时间
        if queue_empty and not message_batch:
            try:
                await asyncio.sleep(0.01) # 轮询间隔, 略微缩短
            except asyncio.CancelledError:
                logger.info(f"[Processor Loop - {process_id}] Cancelled during sleep.")
                if not proc_stop_event.is_set():
                    proc_stop_event.set()
                break # 如果被取消则退出循环

    # logger.info(f"[Processor Loop - {process_id}] Exited.")


# --- 添加辅助函数更新适配器界面 ---
async def update_ui_after_adapter_stop(page: ft.Page, app_state: "AppState"):
    """当适配器进程停止后，更新适配器界面"""
    # 导入 create_adapters_view 函数
    from .ui_views import create_adapters_view
    
    # 找到适配器视图并更新
    for view in page.views:
        if view.route == "/adapters":
            # 简单地重新加载视图
            page.views.remove(view)
            new_adapters_view = create_adapters_view(page, app_state)
            page.views.append(new_adapters_view)
            page.update()
            break


# --- New Generic Start Function ---
def start_managed_process(
    script_path: str,
    type: str,
    display_name: str,
    page: ft.Page,
    app_state: "AppState",
    process_id: str = None,  # 添加可选参数process_id
) -> Tuple[bool, Optional[str]]:
    """
    启动一个受管理的后台进程，创建其状态并启动读取器/处理器
    Starts a managed background process, creates its state, and starts reader/processor.
    
    返回: (是否成功: 布尔值, 消息: 可选字符串)
    Returns: (success: bool, message: Optional[str])
    """
    from .state import ManagedProcessState  # Dynamic import
    


    # 根据类型生成进程ID: mmc类型使用固定ID"mmc"，其他类型基于脚本文件名生成
    if not process_id:
        process_id = f"process_{os.path.basename(script_path).replace('.py', '').replace('.', '_')}"
    
    logger.info(f"[Start Managed] 使用进程ID: {process_id} 运行脚本: {script_path}")

    # 防止重复启动已存在的运行中进程
    existing_state = app_state.managed_processes.get(process_id)
    if (
        existing_state
        and existing_state.status == "running" 
        and existing_state.pid
        and psutil.pid_exists(existing_state.pid)
    ):
        msg = f"进程 '{display_name}' (ID: {process_id}) 已在运行中"
        logger.info(f"[Start Managed] {msg}")
        return False, msg
        
    # 检查脚本文件是否存在
    full_path = script_path
    if not os.path.isabs(script_path):
        full_path = os.path.join(app_state.script_dir, script_path)
    
    if not os.path.exists(full_path):
        msg = f"错误：未找到脚本文件 {script_path}"
        logger.info(f"[启动管理进程] {msg}")
        show_snackbar(page, msg, error=True)
        return False, msg

    logger.info(f"[Start Managed] Preparing to start NEW process: {display_name} ({script_path})")

    # Create NEW state object for this process with its OWN queue and event
    # UNLESS it's bot.py, in which case we still use the old singletons for now
    if type == "mmc":
        is_main_bot = True
    else:
        is_main_bot = False
    logger.info(f"[Start Managed] is_main_bot={is_main_bot}")
    
    # 如果进程之前存在但已经停止，先清理旧的stop_event
    if existing_state and existing_state.stop_event and existing_state.stop_event.is_set():
        logger.info(f"[Start Managed] 清理之前设置的stop_event: {process_id}")
        existing_state.stop_event.clear()
    
    new_queue = app_state.output_queue if is_main_bot else queue.Queue()
    new_event = app_state.stop_event if is_main_bot else threading.Event()

    # 检查是否之前运行过
    has_run_before = False
    if existing_state:
        has_run_before = existing_state.has_run_before
        # 如果适配器之前运行过，重用相同的输出视图以保留之前的日志
        if not is_main_bot and existing_state.output_list_view:
            logger.info(f"[Start Managed] 重用现有适配器输出视图: {process_id}")

    new_process_state = ManagedProcessState(
        process_id=process_id,
        script_path=script_path,
        display_name=display_name,
        output_queue=new_queue,
        stop_event=new_event,
        status="starting",
        has_run_before=has_run_before  # 保留之前的运行状态
    )
    
    # 保留原有输出视图，如果存在的话
    if existing_state and existing_state.output_list_view:
        new_process_state.output_list_view = existing_state.output_list_view
    
    app_state.managed_processes[process_id] = new_process_state


    output_lv: Optional[ft.ListView] = None
    if is_main_bot:
        output_lv = app_state.output_list_view  # Use the main console view
        
        # 如果是mmc进程，清空现有输出视图
        if output_lv and len(output_lv.controls) > 0:
            logger.info(f"[Start Managed - {process_id}] 清空MMC输出视图，准备新会话")
            output_lv.controls.clear()
    else:
        # 适配器进程
        if new_process_state.output_list_view:
            output_lv = new_process_state.output_list_view
            logger.info(f"[Start Managed - {process_id}] 重用已有输出视图，当前行数: {len(output_lv.controls)}")
            # 重启适配器时，清除旧的日志内容
            output_lv.controls.clear()
            logger.info(f"[Start Managed - {process_id}] 已清除适配器旧日志，准备重新启动")
            # 添加分隔标记，表示新启动
            output_lv.controls.append(ft.Text(f"--- 重新启动 {display_name} --- ", italic=True))
        else:
            # 创建新的ListView
            output_lv = ft.ListView(expand=True, spacing=2, padding=5, auto_scroll=True)  # 始终默认开启自动滚动
            new_process_state.output_list_view = output_lv
            output_lv.controls.append(ft.Text(f"--- 启动 {display_name} --- ", italic=True))
    
    # Add starting message to the determined ListView if it's empty (after potential clear)
    # This handles the very first start or if clearing left it empty.
    if output_lv and len(output_lv.controls) == 0: 
        output_lv.controls.append(ft.Text(f"--- 启动 {display_name} --- ", italic=True))
    elif not output_lv: 
        logger.info(f"[Start Managed - {process_id}] Error: Could not determine target ListView.")

    try:
        logger.info(f"[Start Managed - {process_id}] Starting subprocess: {full_path}")
        sub_env = os.environ.copy()
        # Set env vars if needed (e.g., for colorization)
        sub_env["LOGURU_COLORIZE"] = "True"
        sub_env["FORCE_COLOR"] = "1"
        sub_env["SIMPLE_OUTPUT"] = "True"
        logger.info(
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
            logger.info(f"[Start Managed - {process_id}] 使用用户指定的 Python: {executable_path}")
        else:
            # 不再尝试使用内部解释器或当前解释器
            error_msg = "未设置有效的 Python 解释器路径。请在设置中指定 Python 解释器路径。"
            logger.info(f"[Start Managed - {process_id}] {error_msg}")
            
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

        logger.info(f"[Start Managed - {process_id}] 最终命令列表: {cmd_list}")

        # --- 获取用户选择的编码 --- #
        # 从 AppState 中的 gui_config 读取设置，提供默认值 utf-8
        selected_encoding = app_state.gui_config.get("subprocess_encoding", "utf-8")
        logger.info(f"[Start Managed - {process_id}] 使用编码 '{selected_encoding}' 启动子进程 (来自 GUI 设置)")

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
        logger.info(f"[Start Managed - {process_id}] Subprocess started. PID: {process.pid}")

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
        logger.info(f"[Start Managed - {process_id}] Output reader thread started.")


        page.run_task(output_processor_loop,
                    page=page,
                    app_state=app_state,
                    process_id=process_id,
                    output_queue=new_queue,
                    stop_event=new_event,
                    target_list_view=output_lv)
        logger.info(f"[Start Managed - {process_id}] Output processor loop scheduled.")

        return True, f"Process '{display_name}' started successfully."

    except Exception as e:
        logger.info(f"[Start Managed - {process_id}] Error during startup:")
        traceback.logger.info_exc()
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
    logger.info(f"[Start Console] Using bot script path: {bot_script}")
    logger.info(f"[Start Console] 调用start_managed_process,bot_script={bot_script}")
    # --- Call the generic start function --- #
    success, error_message = start_managed_process(
        script_path=bot_script,
        type = "mmc",
        display_name="MaiCore",  # Display name for the main bot
        page=page,
        app_state=app_state,
        process_id="mmc"
    )

    if success:
        logger.info("[Start Console] start_managed_process reported success.")
        page.go("/console")
    else:
        logger.info(f"[Start Console] start_managed_process failed: {error_message}")
        update_buttons_state(page, app_state, is_running=False)


def start_maicore_in_new_window(page: ft.Page, app_state: "AppState"):
    """
    在新命令行窗口中启动MaiCore进程，不在应用内捕获输出。
    """
    bot_script = app_state.bot_script_path
    
    # 检查Python路径是否有效
    if not app_state.python_path or not os.path.exists(app_state.python_path):
        error_msg = "未设置有效的Python解释器路径。请在设置中指定Python解释器路径。"
        logger.info(f"[启动新窗口] {error_msg}")
        show_snackbar(page, error_msg, error=True)
        return False
    
    try:
        logger.info(f"[启动新窗口] 准备启动新窗口中的MaiCore: {bot_script}")
        
        if platform.system() == "Windows":
            # Windows系统使用start命令在新窗口启动
            # 修复Windows下引号嵌套的问题
            python_path = app_state.python_path.replace('"', '')
            bot_script_path = bot_script.replace('"', '')
            cmd = f'start cmd.exe /k {python_path} {bot_script_path}'
            logger.info(f"[启动新窗口] Windows命令: {cmd}")
            subprocess.Popen(cmd, shell=True, cwd=app_state.script_dir)
        else:
            # Linux/Mac系统
            terminal_cmd = "gnome-terminal"  # 默认使用gnome-terminal
            if platform.system() == "Darwin":  # macOS
                terminal_cmd = "open -a Terminal"
            
            cmd = f'{terminal_cmd} -- {app_state.python_path} "{bot_script}"'
            subprocess.Popen(cmd, shell=True, cwd=app_state.script_dir)
            
        logger.info(f"[启动新窗口] 成功启动MaiCore在新窗口")
        show_snackbar(page, "已在新窗口启动MaiCore")
        return True
        
    except Exception as e:
        error_message = str(e) if str(e) else repr(e)
        logger.info(f"[启动新窗口] 启动失败: {error_message}")
        logger.info(traceback.format_exc())
        show_snackbar(page, f"启动MaiCore失败: {error_message}", error=True)
        return False



