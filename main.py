import flet as ft
import os
import sys
import datetime
import logging # <-- Added import
import logging.handlers # For potential future use, not strictly needed for basic setup
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
    create_meme_management_view,
)
from src.MaiGoi.config_manager import load_config, save_config # Removed get_config_path, verify_config_consistency
from src.MaiGoi.ui_console_view import create_console_view
from src.MaiGoi.ui_settings_view import create_settings_view
from src.MaiGoi.db_connector import GUIDBWrapper, close_db_connection # <-- 导入数据库相关
# from src.MaiGoi.config_manager import verify_config_consistency # Removed

from loguru import logger

import asyncio
asyncio.get_event_loop().set_debug(True)


app_state = AppState()


# --- 添加配置路径调试函数 --- # Removed print_config_paths
# --- atexit 清理注册 --- #
# 从process_manager模块注册清理函数
# 它需要访问app_state
# logging automatically registers atexit handlers to flush and close file handlers.
atexit.register(cleanup_on_exit, app_state)
atexit.register(close_db_connection) # <-- 注册数据库关闭函数
logger.info("atexit cleanup handler from process_manager registered.")
logger.info("atexit close_db_connection handler registered.")


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
        logger.info(f"[路由变更 /console] 检查状态: PID={app_state.bot_pid}, 运行中={is_running}, 停止事件={app_state.stop_event.is_set()}")

        if is_running:
            logger.info("[Route Change /console] Process is running.")
        else:
            logger.info("[Route Change /console] Process is not running.")
            # 获取bot.py进程状态并确定显示消息
            bot_process_state = app_state.managed_processes.get("bot.py") # Should this be "mmc"?
            has_run_before = bot_process_state.has_run_before if bot_process_state else False
            not_running_message = "--- Bot 进程已结束，可重新启动 ---" if has_run_before else "--- Bot 进程未运行 ---"
            
            # app_state.output_list_view is now guaranteed to exist.
            # Clear previous controls if it's not empty and the last message isn't already the status message.
            # This avoids duplicate status messages if navigating back and forth.
            if app_state.output_list_view.controls:
                last_control = app_state.output_list_view.controls[-1]
                # Clear only if not already showing a relevant status message
                if not (isinstance(last_control, ft.Text) and last_control.value and 
                        ("Bot 进程未运行" in last_control.value or "Bot 进程已结束" in last_control.value)):
                    # If the console had previous output, we might want to clear it before showing "not running"
                    # For now, let's append. If clearing is desired, uncomment below:
                    # app_state.output_list_view.controls.clear()
                    pass # Decide if clearing is appropriate
            
            # Add or update the status message
            status_message_exists = False
            if app_state.output_list_view.controls:
                last_control = app_state.output_list_view.controls[-1]
                if (isinstance(last_control, ft.Text) and last_control.value and 
                    ("Bot 进程未运行" in last_control.value or "Bot 进程已结束" in last_control.value)):
                    status_message_exists = True
                    if last_control.value != not_running_message: # Update if message changed (e.g. from 'not run' to 'ended')
                        last_control.value = not_running_message
            
            if not status_message_exists:
                app_state.output_list_view.controls.append(ft.Text(not_running_message, italic=True))
            
            # Ensure the console_view is using the (now guaranteed) app_state.output_list_view
            # This might be redundant if create_console_view correctly sets its content to app_state.output_list_view
            # but it's a safeguard.
            # The original problematic line was: if console_view.controls[1].controls[0].content != app_state.output_list_view:
            # Assuming console_view.controls[1].controls[0] is now a Column, and its first child is the container with .content
            potential_column = console_view.controls[1].controls[0]
            if hasattr(potential_column, 'controls') and len(potential_column.controls) > 0: 
                actual_target_control = potential_column.controls[0]
                if hasattr(actual_target_control, 'content'):
                    if actual_target_control.content != app_state.output_list_view:
                        actual_target_control.content = app_state.output_list_view
                else:
                    logger.warning(f"Target control for console_view output_list_view does not have .content attribute. Path: console_view.controls[1].controls[0].controls[0]. Type: {type(actual_target_control)}")
            else:
                logger.warning(f"Console view structure unexpected. Path console_view.controls[1].controls[0] is a {type(potential_column)} but has no sub-controls or is not a Column as expected by fix.")
    elif target_route == "/adapters":
        adapters_view = create_adapters_view(page, app_state)
        page.views.append(adapters_view)
    elif target_route == "/settings":
        # Call the new settings view function
        settings_view = create_settings_view(page, app_state)
        page.views.append(settings_view)
    elif target_route == "/meme-management":
        meme_view = create_meme_management_view(page, app_state)
        page.views.append(meme_view)

    elif target_route.startswith("/adapters/") and len(target_route.split("/")) == 3:
        parts = target_route.split("/")
        process_id = parts[2]  # 提取进程ID (现在使用 adapter_filename 格式)
        logger.info(f"[Route Change] 检测到适配器输出路由: {process_id}")
        adapter_output_view = create_process_output_view(page, app_state, process_id)
        if adapter_output_view:
            page.views.append(adapter_output_view)
        else:
            # 如果视图创建失败（例如，找不到进程状态），返回适配器列表
            logger.warning(f"[Route Change] 为 {process_id} 创建输出视图失败。重定向到 /adapters。")
            # 避免无限循环
            if len(page.views) > 1:  # 确保不弹出主视图
                page.views.pop()  # 弹出失败的视图尝试
            # 查找适配器视图（如果存在），否则创建
            adapters_view_index = -1
            for i, view in enumerate(page.views):
                if view.route == "/adapters":
                    adapters_view_index = i
                    break
            if adapters_view_index == -1:  # 适配器视图不在栈中？添加它
                adapters_view = create_adapters_view(page, app_state)
                page.views.append(adapters_view)
            # 返回适配器列表路由以正确重建视图栈
            page.go("/adapters")
            return  # 防止下面的 page.update()

    # Update the page to show the correct view(s)
    page.update()


def view_pop(e: ft.ViewPopEvent):
    """Handles view popping (e.g., back navigation)."""
    page = e.page
    logger.info(f"[View Pop] Triggered. Current page.views count: {len(page.views)}") # 添加日志

    # --- 增加保护 ---
    # 至少要保留一个视图（通常是主视图），所以只有当视图多于1个时才执行pop和go
    if len(page.views) > 1:
        page.views.pop()
        top_view = page.views[-1]
        logger.info(f"[View Pop] Popped. New top_view route: {top_view.route}. Remaining views: {len(page.views)}")
        # Go to the route of the view now at the top of the stack
        # This will trigger route_change again to rebuild the view stack correctly
        page.go(top_view.route)
    elif len(page.views) == 1:
        logger.warning("[View Pop] Warning: Tried to pop the last view. Doing nothing.")
        # 如果只剩一个视图，通常是主视图，不应该pop它。
        # 可以选择什么都不做，或者导航到主视图的路由以确保状态一致
        # page.go("/") # 可选：如果希望强制回到主页
    else: # page.views is empty
        logger.error("[View Pop] Error: page.views is already empty. Cannot pop. This indicates a severe state issue.")
        # 这种情况下，视图栈已经空了，这是一个严重的问题。
        # 可能需要更复杂的恢复逻辑，或者至少避免进一步的错误。
        # 也许可以尝试强制导航到主页：
        # page.go("/")


def main(page: ft.Page):
    # --- 步骤 0: 设置工作目录为项目根目录 ---
    project_root = Path(__file__).resolve().parent
    os.chdir(project_root)
    logger.info(f"工作目录已设置为: {project_root}")

    # --- 步骤 1: 加载 GUI 配置 ---
    # 路径将是 <project_root>/config/gui_config.toml
    # 如果 config 目录或 gui_config.toml 不存在，load_config 会创建它们（仅对GUI）
    app_state.gui_config = load_config(config_type="gui") # base_dir is not needed for GUI
    if not app_state.gui_config:
        logger.error("无法加载GUI配置，将使用空配置。应用可能无法正常运行。")
        app_state.gui_config = {} # 确保它是一个字典

    # 从GUI配置获取 bot_script_path
    mmc_script_path = app_state.gui_config.get("bot_script_path", "bot.py") # 默认 "bot.py"

    # --- 步骤 2: 解析 mmc_path (bot脚本的根目录) ---
    resolved_mmc_script_path = Path(mmc_script_path).resolve()
    mmc_path = resolved_mmc_script_path.parent  # 获取脚本所在目录作为根目录
    
    app_state.mmc_path = mmc_path  # 存储 mmc_path
    app_state.bot_script_path = str(resolved_mmc_script_path)  # 存储解析后的绝对路径
    logger.info(f"MMC路径 (bot脚本根目录) 设置为: {mmc_path}")
    logger.info(f"Bot脚本路径设置为: {app_state.bot_script_path}")

    # --- 步骤 3: 加载特定于 MMC 的配置 (不创建文件/目录) ---
    # Bot 配置
    app_state.bot_config = load_config(config_type="bot", base_dir=mmc_path)
    if not app_state.bot_config:
        logger.warning(f"未找到Bot配置文件 (期望路径: {mmc_path / 'config' / 'bot_config.toml'}) 或加载失败。")
    else:
        logger.info(f"Bot配置从 {mmc_path / 'config' / 'bot_config.toml'} 加载成功。")
        
    # LPMM 配置
    app_state.lpmm_config = load_config(config_type="lpmm", base_dir=mmc_path)
    if not app_state.lpmm_config:
        logger.warning(f"未找到LPMM配置文件 (期望路径: {mmc_path / 'config' / 'lpmm_config.toml'}) 或加载失败。")
    else:
        logger.info(f"LPMM配置从 {mmc_path / 'config' / 'lpmm_config.toml'} 加载成功。")

    # .env 文件路径
    env_file_path = mmc_path / ".env"
    if env_file_path.is_file():
        logger.info(f".env 文件存在于: {env_file_path}")
    else:
        logger.warning(f".env 文件未找到于: {env_file_path}")
    
    # --- 日志设置 (可以移到更早的位置，如果需要记录配置加载过程) ---
    # setup_logging(app_state.mmc_path) # 如果 setup_logging 依赖 mmc_path

    interest_log_dir = mmc_path / "logs" / "interest" # 日志目录基于 mmc_path
    try:
        interest_log_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"确保兴趣监控日志目录存在: {interest_log_dir}")
        
        interest_log_file = interest_log_dir / "interest_history.log"
        if interest_log_file.exists():
            interest_log_file.unlink() # 删除旧日志
            logger.info(f"已删除旧的兴趣日志文件: {interest_log_file}")
    except Exception as e:
        logger.exception(f"处理兴趣日志目录/文件时出错 {interest_log_dir}: {e}")

    # --- 其他UI和应用状态设置 ---
    # 使用 app_state.gui_config, app_state.bot_config 等进行后续设置
    app_state.adapter_paths = app_state.gui_config.get("adapters", []).copy()
    logger.info(f"从GUI配置加载的适配器路径: {app_state.adapter_paths}")

    python_path_from_config = app_state.gui_config.get("python_path")
    if python_path_from_config:
        py_path_candidate = Path(python_path_from_config)
        if not py_path_candidate.is_absolute():
            # 假设相对路径是相对于 mmc_path
            py_path_candidate = mmc_path / py_path_candidate
        
        resolved_py_path = py_path_candidate.resolve()
        if resolved_py_path.exists(): # 检查可执行文件是否存在
            app_state.python_path = str(resolved_py_path)
            logger.info(f"Python路径从配置加载并解析: {app_state.python_path}")
        else:
            logger.warning(f"配置中的Python路径 '{python_path_from_config}' (解析为 '{resolved_py_path}') 无效或未找到。")
            app_state.python_path = "" # 重置为提示
    else:
        logger.info("配置中未找到Python路径。如果需要，将提示用户。")
        app_state.python_path = ""

    app_state.script_dir = str(project_root / "src") # 或其他相关脚本目录
    logger.info(f"脚本目录在状态中设置为: {app_state.script_dir}")

    # --- Setup File Picker --- #
    app_state.file_picker = ft.FilePicker()
    page.overlay.append(app_state.file_picker)
    logger.info("FilePicker created and added to page overlay.")

    page.title = "MaiBot 启动器"
    page.window.width = 1400
    page.window.height = 1000
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    saved_theme = app_state.gui_config.get("theme", "System").upper()
    try:
        page.theme_mode = ft.ThemeMode[saved_theme]
        logger.info(f"Applied theme from config: {page.theme_mode}")
    except KeyError:
        logger.warning(f"Invalid theme '{saved_theme}' in config. Falling back to System.")
        page.theme_mode = ft.ThemeMode.SYSTEM
        
    MAIN_STYLE_COLOR = ft.Colors.ORANGE_ACCENT_200
    MAIN_STYLE_COLOR_DARK = ft.Colors.INDIGO_800
    SURFACE_COLOR_DARK = ft.Colors.INDIGO_600
    SURFACE_COLOR = ft.Colors.ORANGE_50
    SEC_MAIN_SHAPE_COLOR = ft.Colors.PURPLE_200
    SEC_MAIN_SHAPE_COLOR_DARK = ft.Colors.BLUE_900

    dark_theme = ft.Theme(
        color_scheme_seed=MAIN_STYLE_COLOR_DARK, 
        color_scheme=ft.ColorScheme(
            tertiary=MAIN_STYLE_COLOR_DARK,
            secondary=SEC_MAIN_SHAPE_COLOR_DARK,
            inverse_surface=SURFACE_COLOR_DARK,
        )
    )
    
    light_theme = ft.Theme(
        color_scheme_seed=MAIN_STYLE_COLOR, 
        color_scheme=ft.ColorScheme(
            tertiary=MAIN_STYLE_COLOR,
            secondary=SEC_MAIN_SHAPE_COLOR,
            inverse_surface=SURFACE_COLOR,
        )
    )
    
    page.theme = light_theme
    page.dark_theme = dark_theme

    if not hasattr(app_state, 'bot_base_dir'):
        app_state.bot_base_dir = mmc_path 
        logger.info(f"Stored bot_base_dir in AppState (fallback): {app_state.bot_base_dir}")

    # --- 初始化数据库访问 --- #
    # mmc_path 此时已经解析完毕并存储在 app_state.mmc_path 中
    # app_state.gui_db = get_gui_db(app_state.mmc_path) # 直接获取db实例，如果需要立即使用
    # 或者使用包装器实现更彻底的懒加载，并能在需要时重新评估 mmc_path (如果它可能改变)
    app_state.gui_db = GUIDBWrapper(lambda: app_state.mmc_path)
    logger.info(f"数据库访问已通过 GUIDBWrapper 设置 (与 app_state.mmc_path: {app_state.mmc_path} 关联)")
    # 你可以在这里尝试一次数据库连接，以尽早发现问题
    # try:
    #     if app_state.gui_db is not None:
    #        app_state.gui_db.command('ping') # 尝试ping数据库
    #        logger.info("成功 ping 数据库服务器。")
    # except Exception as e:
    #    logger.error(f"初始化时 ping 数据库失败: {e}")

    page.padding = 0

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    page.on_disconnect = lambda e: handle_disconnect(page, app_state, e)
    logger.info("Registered page.on_disconnect handler.")

    page.window_prevent_close = True

    page.go(page.route if page.route else "/")


if __name__ == "__main__":
    print("正在启动中......")
    ft.app(
        target=main,
        port=8077
    )
    logging.info("Flet app exited. atexit handler should run next.")


