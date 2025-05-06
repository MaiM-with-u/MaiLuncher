import flet as ft
from typing import Optional, TYPE_CHECKING
import psutil
import asyncio

# Import components and state
from .flet_interest_monitor import InterestMonitorDisplay
from .process_manager import update_buttons_state  # 动态导入

if TYPE_CHECKING:
    from .state import AppState

# 主控室视图
def create_console_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """创建控制台输出视图 ('/console')，包括兴趣监控。"""
    # 初始化自动滚动状态
    app_state.is_auto_scroll_enabled = True
    
    # 获取或创建输出列表视图
    output_list_view = app_state.output_list_view
    interest_monitor = app_state.interest_monitor_control
    if not output_list_view:
        output_list_view = ft.ListView(
            expand=True,
            spacing=2,
            auto_scroll=app_state.is_auto_scroll_enabled,
            padding=5
        )
        app_state.output_list_view = output_list_view
        print("[控制台视图] 创建了备用ListView")

    # 获取或创建兴趣监控器实例
    if not interest_monitor:
        print("[控制台视图] 创建新的InterestMonitorDisplay实例")
        interest_monitor = InterestMonitorDisplay()
        app_state.interest_monitor_control = interest_monitor

    # --- 为控制台输出和兴趣监控创建容器，以便动态调整大小 --- #
    output_container = ft.Container(
        content=output_list_view,
        expand=4,  # 在左侧 Column 内部分配比例
        border=ft.border.only(bottom=ft.border.BorderSide(1, ft.colors.OUTLINE)),
    )

    monitor_container = ft.Container(
        content=interest_monitor,
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
    interest_monitor.on_toggle = on_monitor_toggle

    # --- Auto-scroll toggle button callback (remains separate) --- #
    # 自动滚动切换按钮回调函数 (保持独立)
    def toggle_auto_scroll(e):
        # Toggle auto-scroll state
        # 切换自动滚动状态
        app_state.is_auto_scroll_enabled = not app_state.is_auto_scroll_enabled
        
        # Get list view reference and update its auto-scroll setting
        # 获取列表视图引用并更新其自动滚动设置
        lv = app_state.output_list_view  # Get potentially updated list view / 获取可能已更新的列表视图
        if lv:
            lv.auto_scroll = app_state.is_auto_scroll_enabled

            # When disabling auto-scroll, record current scroll position
            # 当关闭自动滚动时，记录当前滚动位置
            if not app_state.is_auto_scroll_enabled:
                # Mark view in manual viewing mode to maintain position during updates
                # 标记视图为手动观看模式，以便在更新时保持位置
                app_state.manual_viewing = True
            else:
                # When enabling auto-scroll, disable manual viewing mode
                # 开启自动滚动时，关闭手动观看模式
                app_state.manual_viewing = False

        # Update button text display
        # 更新按钮文本显示
        text_control = e.control.data if isinstance(e.control.data, ft.Text) else None
        if text_control:
            text_control.value = "自动滚动 开" if app_state.is_auto_scroll_enabled else "自动滚动 关"
        else:
            print("[toggle_auto_scroll] Warning: Could not find Text control in button data.")
            # 警告：无法在按钮数据中找到文本控件

        # Update tooltip and log status
        # 更新工具提示并记录状态
        e.control.tooltip = "切换控制台自动滚动"  # Toggle console auto-scroll / 切换控制台自动滚动
        print(f"Auto-scroll {'enabled' if app_state.is_auto_scroll_enabled else 'disabled'}.", flush=True)
        
        # Refresh button UI
        # 刷新按钮UI
        e.control.update()  # Try updating only the container first / 先尝试仅更新容器
        
    

    # --- Card Styling (Copied from create_main_view for reuse) --- #
    card_shadow = ft.BoxShadow(
        spread_radius=1,
        blur_radius=10,
        color=ft.colors.with_opacity(0.2, ft.colors.BLACK87),
        offset=ft.Offset(1, 2),
    )
    card_radius = ft.border_radius.all(4)
    card_bgcolor = ft.colors.with_opacity(0.65, ft.colors.PRIMARY_CONTAINER)
    card_padding = ft.padding.symmetric(vertical=8, horizontal=12)  # Smaller padding for console buttons

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
        # Remove left margin
        margin=ft.margin.only(right=10),
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
            ft.Text("..."),  # 下半部分占位符
            # 将按钮放在底部
            # Wrap the Row in a Container to apply padding
            ft.Container(
                content=ft.Row(
                    [console_action_button, toggle_button],
                    # alignment=ft.MainAxisAlignment.SPACE_AROUND,
                    alignment=ft.MainAxisAlignment.START,  # Align buttons to the start
                ),
                # Apply padding to the container holding the row
                padding=ft.padding.only(bottom=10),
            ),
        ],
        # height=100, # 可以给下半部分固定高度，或者让它自适应
        spacing=5,
        # Remove padding from the Column itself
        # padding=ft.padding.only(bottom=10)
    )
    info_column = ft.Column(
        controls=[
            info_top_section,
            info_bottom_section,
        ],
        width=250,  # 增加宽度
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