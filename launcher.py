import flet as ft
import os
import atexit
import psutil
from pathlib import Path
from src.MaiGoi.state import AppState
from src.MaiGoi.process_manager import (
    cleanup_on_exit,
    handle_disconnect,
)
from src.MaiGoi.ui_views import (
    create_main_view,
    create_adapters_view,
    create_process_output_view,
)
from src.MaiGoi.config_manager import load_config
from src.MaiGoi.ui_console_view import create_console_view
from src.MaiGoi.ui_settings_view import create_settings_view
app_state = AppState()

# --- atexit 清理注册 --- #
# 从process_manager模块注册清理函数
# 它需要访问app_state
atexit.register(cleanup_on_exit, app_state)
print("[Main Script] atexit cleanup handler from process_manager registered.", flush=True)



def route_change(route: ft.RouteChangeEvent):
    """Handles Flet route changes, creating and appending views."""
    page = route.page
    target_route = route.route

    # 清空页面
    page.views.clear()

    # Always add the main view
    main_view = create_main_view(page, app_state)
    page.views.append(main_view)

    # 前往主控室
    if target_route == "/console":
        console_view = create_console_view(page, app_state)
        page.views.append(console_view)

        # Check process status and potentially restart processor loop if needed
        is_running = app_state.bot_pid is not None and psutil.pid_exists(app_state.bot_pid)
        print(f"[路由变更 /console] 检查状态: PID={app_state.bot_pid}, 运行中={is_running}, 停止事件={app_state.stop_event.is_set()}", flush=True)

        if is_running:
            print("[Route Change /console] Process is running.", flush=True)
            # if app_state.stop_event.is_set():
            #     print("[Route Change /console] Stop event was set, clearing and restarting processor loop.", flush=True)
            #     app_state.stop_event.clear()

            #     print(f"启动processor_loop前检查：output_list_view = {app_state.output_list_view}, 控件数 = {len(app_state.output_list_view.controls) if app_state.output_list_view else 0}")
            #     print(f"output_list_view.visible = {app_state.output_list_view.visible if app_state.output_list_view else 'N/A'}")
                

            #     page.run_task(
            #         output_processor_loop, 
            #         page, 
            #         app_state,
            #         "bot.py",                      # 明确指定process_id 
            #         app_state.output_queue,        # 明确传递队列
            #         app_state.stop_event,          # 明确传递事件
            #         app_state.output_list_view     # 明确传递ListView
            #     )
            #     print("[Route Change /console] 已启动processor_loop，参数完整传递")
        else:
            print("[Route Change /console] Process is not running.", flush=True)
            # 获取bot.py进程状态并确定显示消息
            bot_process_state = app_state.managed_processes.get("bot.py")
            has_run_before = bot_process_state.has_run_before if bot_process_state else False
            not_running_message = "--- Bot 进程已结束，可重新启动 ---" if has_run_before else "--- Bot 进程未运行 ---"
            
            # 确保ListView存在
            if not app_state.output_list_view:
                print("[Route Change /console] Creating ListView to show status message.")
                app_state.output_list_view = ft.ListView(
                    expand=True, spacing=2, auto_scroll=app_state.is_auto_scroll_enabled, padding=5
                )
                app_state.output_list_view.controls.append(ft.Text(not_running_message, italic=True))
                console_view.controls[1].controls[0].content = app_state.output_list_view
                return
            
            # 检查是否已有状态消息
            status_message_exists = False
            if app_state.output_list_view.controls:
                last_control = app_state.output_list_view.controls[-1]
                if (isinstance(last_control, ft.Text) and last_control.value and 
                    ("Bot 进程未运行" in last_control.value or "Bot 进程已结束" in last_control.value)):
                    # 已有状态消息，如果需要更新则更新
                    status_message_exists = True
                    if last_control.value != not_running_message:
                        last_control.value = not_running_message
            
            # 如果没有状态消息，添加一个
            if not status_message_exists:
                app_state.output_list_view.controls.append(ft.Text(not_running_message, italic=True))
    elif target_route == "/adapters":
        adapters_view = create_adapters_view(page, app_state)
        page.views.append(adapters_view)
    elif target_route == "/settings":
        # Call the new settings view function
        settings_view = create_settings_view(page, app_state)
        page.views.append(settings_view)

    elif target_route.startswith("/adapters/") and len(target_route.split("/")) == 3:
        parts = target_route.split("/")
        process_id = parts[2]  # Extract the process ID (which is the script path for now)
        print(f"[Route Change] Detected adapter output route for ID: {process_id}")
        adapter_output_view = create_process_output_view(page, app_state, process_id)
        if adapter_output_view:
            page.views.append(adapter_output_view)
        else:
            # If view creation failed (e.g., process state not found), show error and stay on previous view?
            # Or redirect back to /adapters? Let's go back to adapters list.
            print(f"[Route Change] Failed to create output view for {process_id}. Redirecting to /adapters.")
            # Avoid infinite loop if /adapters also fails
            if len(page.views) > 1:  # Ensure we don't pop the main view
                page.views.pop()  # Pop the failed view attempt
            # Find the adapters view if it exists, otherwise just update
            adapters_view_index = -1
            for i, view in enumerate(page.views):
                if view.route == "/adapters":
                    adapters_view_index = i
                    break
            if adapters_view_index == -1:  # Adapters view wasn't in stack? Add it.
                adapters_view = create_adapters_view(page, app_state)
                page.views.append(adapters_view)
            # Go back to the adapters list route to rebuild the view stack correctly
            page.go("/adapters")
            return  # Prevent page.update() below

    # Update the page to show the correct view(s)
    page.update()


def view_pop(e: ft.ViewPopEvent):
    """Handles view popping (e.g., back navigation)."""
    page = e.page
    # Remove the top view
    page.views.pop()
    if page.views:
        top_view = page.views[-1]
        # Go to the route of the view now at the top of the stack
        # This will trigger route_change again to rebuild the view stack correctly
        page.go(top_view.route)
    # else: print("Warning: Popped the last view.")


def main(page: ft.Page):
    # 清理旧日志文件
    log_path = "logs/interest/interest_history.log"
    if os.path.exists(log_path):
        os.remove(log_path)

    # 加载初始GUI配置
    initial_gui_config = load_config(config_type="gui")
    app_state.gui_config = initial_gui_config
    app_state.bot_script_path = app_state.gui_config.get("bot_script_path", "bot.py")  # 使用默认值如果配置不存在
    
    print(f"[Main] 初始bot脚本路径: {app_state.bot_script_path}")

    # 解析为绝对路径
    bot_script_abs_path = Path(app_state.bot_script_path).resolve()
    print(f"[Main] 解析后的bot脚本路径: {bot_script_abs_path}")


    
    if not bot_script_abs_path.is_file():
        # 即使文件不存在，我们也使用其父目录作为 bot_base_dir
        print(f"[Main] 警告: Bot 脚本 '{app_state.bot_script_path}' (解析为 '{bot_script_abs_path}') 不存在，但仍使用其父目录")
        bot_base_dir = bot_script_abs_path.parent
        print(f"[Main] 已设置 bot_base_dir 为: {bot_base_dir}")
    else:
        bot_base_dir = bot_script_abs_path.parent
        print(f"[Main] 成功！已确定 bot base directory: {bot_base_dir}")
        
    # 额外检查：验证config目录是否存在
    config_dir = bot_base_dir / "config"
    if not config_dir.exists():
        print(f"[Main] 警告：在 {bot_base_dir} 下没有找到 config 目录，尝试创建...")
        try:
            config_dir.mkdir(exist_ok=True)
            print(f"[Main] 已创建config目录: {config_dir}")
        except Exception as e:
            print(f"[Main] 创建config目录失败: {e}")
    
    # Debug: 调试信息
    print(f"[Main] 最终确定的 bot_base_dir: {bot_base_dir}")
    app_state.bot_base_dir = bot_base_dir # Store for potential use elsewhere (e.g., saving config)

    # --- Reload GUI config relative to bot directory --- #
    # Now that we have the bot_base_dir, reload the GUI config from the correct location
    if bot_base_dir is not None:
        print(f"[Main] 从 bot 目录重新加载 GUI 配置: {bot_base_dir}")
        try:
            loaded_config = load_config(config_type="gui", base_dir=bot_base_dir)
            app_state.gui_config = loaded_config # Update state with correctly loaded config
            print(f"[Main] 成功从 {bot_base_dir} 加载配置")
        except Exception as e:
            print(f"[Main] 从 bot 目录加载配置失败: {e}, 将使用初始配置")
            loaded_config = initial_gui_config
    else:
        print("[Main] 警告: bot_base_dir 为 None，无法从 bot 目录加载配置，将使用初始加载的配置")
        loaded_config = initial_gui_config

    # --- Load other settings from the correctly loaded GUI config --- #
    app_state.adapter_paths = loaded_config.get("adapters", []).copy()
    
    # 重要：不要覆盖已经确定的bot_script_path
    # 只有在bot_script_path为空或无效时才使用配置中的值
    if not app_state.bot_script_path:
        app_state.bot_script_path = loaded_config.get("bot_script_path", "bot.py") 
        print(f"[Main] 从配置加载 bot_script_path: {app_state.bot_script_path}")

    # 加载用户自定义的 Python 路径 (from correctly loaded config)
    if "python_path" in loaded_config and loaded_config["python_path"] and Path(loaded_config["python_path"]).exists():
        app_state.python_path = str(Path(loaded_config["python_path"]).resolve()) # Store absolute path
        print(f"[Main] 从相对于 Bot 的配置加载 Python 路径: {app_state.python_path}")
    else:
        print(f"[Main] Python path not found or invalid in config. Will prompt if needed.")
        app_state.python_path = "" # Ensure it's empty if not valid

    print(f"[Main] Final adapters loaded: {app_state.adapter_paths}")

    # Set script_dir in AppState early
    app_state.script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"[Main] Script directory set in state: {app_state.script_dir}", flush=True)

    # --- Setup File Picker --- #
    # Create the FilePicker instance
    # The on_result handler will be set dynamically in the view that uses it
    app_state.file_picker = ft.FilePicker()
    # Add the FilePicker to the page's overlay controls
    page.overlay.append(app_state.file_picker)
    print("[Main] FilePicker created and added to page overlay.")

    page.title = "MaiBot 启动器"
    page.window.width = 1400
    page.window.height = 1000  # Increased height slightly for monitor
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # --- Apply Theme from Config --- #
    saved_theme = app_state.gui_config.get("theme", "System").upper()
    try:
        page.theme_mode = ft.ThemeMode[saved_theme]
        print(f"[Main] Applied theme from config: {page.theme_mode}")
    except KeyError:
        print(f"[Main] Warning: Invalid theme '{saved_theme}' in config. Falling back to System.")
        page.theme_mode = ft.ThemeMode.SYSTEM
        
    # --- 自定义主题颜色 --- #
    # 创建深色主题，使橙色变得更暗
    dark_theme = ft.Theme(
        color_scheme_seed=ft.colors.ORANGE,
        primary_color=ft.colors.ORANGE_700,  # 使用更暗的橙色
        color_scheme=ft.ColorScheme(
            primary=ft.colors.ORANGE_700,
            primary_container=ft.colors.ORANGE_800,
        )
    )
    
    # 创建亮色主题
    light_theme = ft.Theme(
        color_scheme_seed=ft.colors.ORANGE,
    )
    
    # 设置自定义主题
    page.theme = light_theme
    page.dark_theme = dark_theme

    # Add the base directory to AppState if it's not already there
    if not hasattr(app_state, 'bot_base_dir'):
        # This check is redundant given the code above, but safe
        app_state.bot_base_dir = bot_base_dir 
        print(f"[Main] Stored bot_base_dir in AppState: {app_state.bot_base_dir}")

    page.padding = 0  # <-- 将页面 padding 设置为 0


    # --- Routing Setup --- #
    page.on_route_change = route_change
    page.on_view_pop = view_pop

    # --- Disconnect Handler --- #
    # Pass app_state to the disconnect handler
    page.on_disconnect = lambda e: handle_disconnect(page, app_state, e)
    print("[Main] Registered page.on_disconnect handler.", flush=True)

    # Prevent immediate close to allow cleanup
    page.window_prevent_close = True


    # --- Initial Navigation --- #
    # Trigger the initial route change to build the first view
    page.go(page.route if page.route else "/")


# --- Run Flet App --- #
if __name__ == "__main__":
    # No need to initialize globals here anymore, AppState handles it.
    ft.app(target=main)
    # This print will appear *after* the Flet window closes,
    # but *before* the atexit handler runs.
    print("[Main Script] Flet app exited. atexit handler should run next.", flush=True)


