import flet as ft
from typing import Optional, TYPE_CHECKING
import psutil
import asyncio
import os
from pathlib import Path

# Import components and state
from .flet_interest_monitor import InterestMonitorDisplay
from .process_manager import update_buttons_state, start_maicore_in_new_window  # 动态导入

if TYPE_CHECKING:
    from .state import AppState

# 主控室视图
def create_console_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """创建控制台输出视图 ('/console')，包括兴趣监控。"""
    # 初始化自动滚动状态
    app_state.is_auto_scroll_enabled = True
    
    # 获取或创建输出列表视图
    output_list_view = app_state.output_list_view
    # Ensure auto_scroll is set according to app_state, as it might have been changed elsewhere
    # or if the ListView was just initialized in AppState with a default.
    output_list_view.auto_scroll = app_state.is_auto_scroll_enabled
    
    # --- Interest Monitor ---
    # 检查 app_state 中是否已经有 interest_monitor_control
    if not app_state.interest_monitor_control:
        print("[控制台视图] 创建新的InterestMonitorDisplay实例")
        # 在创建 InterestMonitorDisplay 实例时，传递 app_state
        app_state.interest_monitor_control = InterestMonitorDisplay()
        
        # 设置日志路径 (如果需要，并且 app_state.bot_base_dir 可用)
        if hasattr(app_state, 'bot_base_dir') and app_state.bot_base_dir:
            log_dir_path = str(app_state.bot_base_dir)
            # InterestMonitorDisplay 的 set_log_path 期望的是 interest_history.log 所在的目录
            # 即 bot_base_dir 本身，因为 set_log_path 内部会拼接 "logs/interest/interest_history.log"
            app_state.interest_monitor_control.set_log_path(log_dir_path)
            print(f"[控制台视图] 设置兴趣监控日志路径到: {log_dir_path}")
        else:
            print("[控制台视图] 警告: bot_base_dir 未在 app_state 中设置，无法配置兴趣监控日志路径。")
            
    interest_monitor_section = app_state.interest_monitor_control
    
    # --- 为控制台输出和兴趣监控创建容器，以便动态调整大小 --- #
    output_container = ft.Container(
        content=output_list_view,
        expand=4,  # 在左侧 Column 内部分配比例
        border=ft.border.only(bottom=ft.border.BorderSide(1, ft.colors.OUTLINE)),
    )

    monitor_container = ft.Container(
        content=interest_monitor_section,
        expand=4,  # 在左侧 Column 内部分配比例
    )

    # --- 设置兴趣监控的切换回调函数 --- #
    def on_monitor_toggle(is_expanded):
        if is_expanded:
            # 监控器展开时，恢复原比例
            output_container.expand = 4
            monitor_container.expand = 4
        else:
            # 监控器隐藏时，让输出区占据更多空间
            output_container.expand = 9
            monitor_container.expand = 0

        # 更新容器以应用新布局
        output_container.update()
        monitor_container.update()

    # 为监控器设置回调函数
    interest_monitor_section.on_toggle = on_monitor_toggle

    def toggle_auto_scroll(e):
        # 切换自动滚动状态
        app_state.is_auto_scroll_enabled = not app_state.is_auto_scroll_enabled
        
        # 更新列表视图设置
        if lv := app_state.output_list_view:
            lv.auto_scroll = app_state.is_auto_scroll_enabled
            app_state.manual_viewing = not app_state.is_auto_scroll_enabled

        # 更新按钮文本
        if isinstance(e.control.data, ft.Text):
            e.control.data.value = "自动滚动 开" if app_state.is_auto_scroll_enabled else "自动滚动 关"
        
        # 更新UI
        e.control.tooltip = "切换控制台自动滚动"
        e.control.update()
        
    

    # --- Card Styling (Copied from create_main_view for reuse) --- #
    card_shadow = ft.BoxShadow(
        spread_radius=1,
        blur_radius=10,
        color=ft.colors.with_opacity(0.2, ft.colors.BLACK87),
        offset=ft.Offset(1, 2),
    )
    card_radius = ft.border_radius.all(4)
    card_bgcolor = ft.colors.with_opacity(0.65, ft.colors.PRIMARY_CONTAINER)
    card_padding = ft.padding.symmetric(vertical=6, horizontal=8)  # 从vertical=8, horizontal=12减小

    # --- Create Buttons --- #
    # Create the main action button (Start/Stop) as a styled Container
    console_action_button_text = ft.Text("...")  # Placeholder text, updated by update_buttons_state
    console_action_button = ft.Container(
        content=console_action_button_text,
        bgcolor=card_bgcolor,  # Apply style
        border_radius=card_radius,
        shadow=card_shadow,
        padding=card_padding,
        ink=True,
        # on_click is set by update_buttons_state
    )
    app_state.console_action_button = console_action_button  # Store container ref

    # 创建在新窗口启动的按钮
    new_window_button_text = ft.Text("新窗口启动", size=12)
    new_window_button = ft.Container(
        content=new_window_button_text,
        tooltip="在新命令行窗口启动MaiCore",
        on_click=lambda e: start_maicore_in_new_window(page, app_state),
        bgcolor=ft.colors.with_opacity(0.6, ft.colors.BLUE_ACCENT_100),
        border_radius=card_radius,
        shadow=card_shadow,
        padding=card_padding,
        ink=True,
        # 使用负边距将按钮向左移动
        margin=ft.margin.only(left=-2),
    )

    # Create the auto-scroll toggle button as a styled Container with Text
    auto_scroll_text_content = "自动滚动 开" if app_state.is_auto_scroll_enabled else "自动滚动 关"
    auto_scroll_text = ft.Text(auto_scroll_text_content, size=12)
    toggle_button = ft.Container(
        content=auto_scroll_text,
        tooltip="切换控制台自动滚动",
        on_click=toggle_auto_scroll,  # Attach click handler here
        bgcolor=card_bgcolor,  # Apply style
        border_radius=card_radius,
        shadow=card_shadow,
        padding=card_padding,
        ink=True,
        # 移除右侧边距
        # margin=ft.margin.only(right=10),
    )
    # Store the text control inside the toggle button container for updating
    toggle_button.data = auto_scroll_text  # Store Text reference in data attribute

    # --- 附加信息区 Column (在 View 级别创建) ---
    info_top_section = ft.Column(
        controls=[
            ft.Text("附加信息", weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("..."),  # 上半部分占位符
        ],
        expand=True,  # 让上半部分填充可用垂直空间
        scroll=ft.ScrollMode.ADAPTIVE,
    )
    info_bottom_section = ft.Column(
        controls=[
            ft.Text("操作按钮", weight=ft.FontWeight.BOLD),
            ft.Divider(),
            # 第一行：创建一个Stack来叠放两个按钮而不是使用Row，以便更精确控制位置
            ft.Stack(
                [
                    console_action_button,  # 启动MaiCore按钮
                    ft.Container(
                        content=new_window_button,
                        alignment=ft.alignment.center_right,
                        margin=ft.margin.only(right=10),
                    ),
                ],
                height=40,  # 设置一个固定高度
            ),
            # 第二行：自动滚动按钮单独一行
            ft.Container(
                content=toggle_button,  # 自动滚动按钮
                padding=0,  # 移除内边距
                margin=ft.margin.only(top=8),  # 只保留上边距
            ),
        ],
        # 给底部区域设置固定最小高度，确保有足够空间显示所有按钮
        height=150,
        spacing=5,
    )
    info_column = ft.Column(
        controls=[
            info_top_section,
            info_bottom_section,
        ],
        width=260,  # 将宽度从250增加到300
        spacing=10,  # 分区之间的间距
    )

    # --- Set Initial Button State --- #
    is_initially_running = app_state.bot_pid is not None and psutil.pid_exists(app_state.bot_pid)
    update_buttons_state(page, app_state, is_running=is_initially_running)

    # --- 视图整体布局结构 ---
    # 1. 最外层是 View 组件，路由为 "/console"
    # 2. 包含两个主要部分:
    #    - AppBar: 顶部标题栏
    #    - Row: 主内容区域，分为左右两栏
    console_view = ft.View(
        "/console",  # 视图路由路径
        [
            # 顶部标题栏
            ft.AppBar(title=ft.Text("Mai控制台")),
            # 主内容区域 - 使用 Row 实现左右分栏布局
            ft.Row(
                controls=[
                    # 左侧区域 - 可扩展的内容区
                    ft.Column(
                        controls=[
                            output_container,  # 控制台输出容器
                            monitor_container, # 监控信息容器
                        ],
                        expand=True,  # 占据 Row 的剩余空间
                    ),
                    
                    # 右侧区域 - 固定宽度的信息栏
                    info_column,  # 包含操作按钮和附加信息
                ],
                expand=True,  # 填满 AppBar 下方的可用空间
            ),
        ],
        padding=0,  # 移除视图内边距
    )


    # 我还是不太明白为什么这段代码可以work
    async def delayed_check():
        # 确保视图已经完全构建
        await asyncio.sleep(0)
        if not app_state.python_path:
            dlg_instance = ft.AlertDialog(
                title=ft.Text("设置 Python 路径"),
                content=ft.Text("请在设置中设置 Python 路径，以便正常运行 Bot 和适配器。"),
                actions=[
                    ft.TextButton("确定", on_click=lambda e: page.close(dlg_instance)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.open(dlg_instance)
    
    page.run_task(delayed_check)

    return console_view