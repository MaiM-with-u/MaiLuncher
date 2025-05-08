import flet as ft
from typing import Optional, TYPE_CHECKING
import psutil
import os
import sys
from .utils import show_snackbar  # Removed run_script import
from .meme_manager import build_meme_grid # <-- Import the new builder function

if TYPE_CHECKING:
    from .state import AppState
    
# 背景色调
BG_LIGHT_COLOR = ft.Colors.with_opacity(0.65, ft.Colors.PRIMARY_CONTAINER)
# 文本颜色
TEXT_COLOR = ft.Colors.ON_SURFACE
TEXT_LIGHT_COLOR = ft.Colors.with_opacity(0.7, ft.Colors.ON_SURFACE)
TEXT_INVERSE_COLOR = ft.Colors.WHITE
# 卡片颜色
CARD_BG_COLOR = ft.Colors.SURFACE
CARD_SHADOW_COLOR = ft.Colors.with_opacity(0.2, ft.Colors.BLACK87)
# 按钮颜色
SIMPLE_BUTTON_COLOR = ft.Colors.ON_PRIMARY
SIMPLE_BUTTON_HOVER_COLOR = ft.Colors.PRIMARY    
    

# --- 添加资源路径处理函数 ---
def get_asset_path(relative_path: str) -> str:
    """
    获取资源文件的正确路径，在打包环境和源码环境下都能正常工作。

    Args:
        relative_path: 相对于项目根目录的资源路径，例如 "src/MaiGoi/assets/image.png"

    Returns:
        str: 资源文件的绝对路径
    """
    # 检查是否在打包环境中运行
    if getattr(sys, "frozen", False):
        # 打包环境
        # 获取应用程序所在目录
        base_dir = os.path.dirname(sys.executable)

        # 尝试多种可能的路径
        possible_paths = [
            os.path.join(base_dir, os.path.basename(relative_path)),
            os.path.join(base_dir, "_internal", relative_path),
        ]

        # 尝试所有可能的路径
        for path in possible_paths:
            if os.path.exists(path):
                print(f"[AssetPath] 打包环境: 找到资源 '{relative_path}' 位置: {path}")
                return path

        # 如果找不到任何匹配的路径，记录错误并返回原始路径
        print(f"[AssetPath] 警告: 在打包环境中找不到资源 '{relative_path}'")
        return os.path.join(base_dir, relative_path)  # 返回可能的路径，以便更容易识别错误
    else:
        # 源码环境，直接使用相对路径
        # 假设 cwd 是项目根目录
        root_dir = os.getcwd()
        path = os.path.join(root_dir, relative_path)

        # 验证路径是否存在
        if os.path.exists(path):
            return path
        else:
            print(f"[AssetPath] 警告: 在源码环境中找不到资源 '{relative_path}'")
            return relative_path  # 返回原始路径，方便调试


def create_main_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """Creates the main view ('/') of the application."""
    # --- Refs for UI manipulation ---
    # Ref对象用于引用和控制界面元素
    # 创建这些引用以便稍后能访问和操作这些控件
    ref_main_button_shape_container = ft.Ref[ft.Container]()  # 背景形状容器的引用
    ref_main_cards_column = ft.Ref[ft.Column]()  # 主卡片列内容的引用
    ref_main_cards_column_container = ft.Ref[ft.Container]()  # 主卡片列容器的引用(用于动画)
    ref_active_tool_display_container = ft.Ref[ft.Container]()  # 工具显示容器的引用

    # --- Set Page Padding to Zero --- #
    page.padding = 0


    from .utils import run_script  # Dynamic import to avoid cycles

    # --- Card Styling --- #
    card_shadow = ft.BoxShadow(
        spread_radius=1,
        blur_radius=10,  # Slightly more blur for frosted effect
        color=CARD_SHADOW_COLOR,
        offset=ft.Offset(1, 2),
    )
    # card_border = ft.border.all(1, ft.colors.with_opacity(0.5, ft.colors.SECONDARY)) # Optional: Remove border for cleaner glass look
    card_radius = ft.border_radius.all(4)  # Slightly softer edges for glass
    # card_bgcolor = ft.colors.with_opacity(0.05, ft.colors.BLUE_GREY_50) # Subtle background
    # Use a semi-transparent primary color for the frosted glass effect
    _card_bgcolor = BG_LIGHT_COLOR  # 使用自定义颜色

    # --- Card Creation Function --- #
    def create_action_card(
        page: ft.Page,
        icon: str,
        subtitle: str,
        text: str,
        on_click_handler,
        tooltip: str = None,
        width: int = 450,
        height: int = 150,
    ):
        # Removed icon parameter usage
        subtitle_text = subtitle
        card_bgcolor_theme = CARD_BG_COLOR  # 使用自定义颜色
        main_text_color_theme = TEXT_COLOR  # 使用自定义颜色
        subtitle_color_theme = TEXT_LIGHT_COLOR  # 使用自定义颜色

        # --- 使用辅助函数获取Emoji图片路径 --- #
        emoji_image_path = get_asset_path("src/MaiGoi/assets/button_shape.png")  # 使用辅助函数获取正确路径

        # --- Create Text Content --- #
        text_content_column = ft.Column(
            [
                # --- Main Title Text ---
                ft.Container(
                    content=ft.Text(
                        text,
                        weight=ft.FontWeight.W_800,
                        size=50,
                        text_align=ft.TextAlign.LEFT,
                        font_family="SimSun",
                        # color=ft.colors.BLACK,
                        color=main_text_color_theme,  # Use theme color
                    ),
                    margin=ft.margin.only(top=-5),
                ),
                # --- Subtitle Text (Wrapped in Container for Margin) ---
                ft.Container(
                    content=ft.Text(
                        subtitle_text,
                        weight=ft.FontWeight.BOLD,
                        size=20,
                        # color=ft.colors.with_opacity(0.7, ft.colors.GREY_500),
                        color=subtitle_color_theme,  # Use theme color
                        text_align=ft.TextAlign.LEFT,
                        font_family="SimHei",
                    ),
                    margin=ft.margin.only(top=-20, left=10),
                ),
            ],
            spacing=0,
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.START,
        )

        # --- Create Emoji Image Layer --- #
        emoji_image_layer = ft.Container(
            content=ft.Image(
                src=emoji_image_path,
                fit=ft.ImageFit.COVER,  # <-- Change fit to COVER for zoom/fill effect
            ),
            alignment=ft.alignment.center,  # Center the image within the container
            # Position the container itself to overlap the right side
            right=-100,  # <-- Allow container to extend beyond the right edge slightly
            top=10,  # <-- Allow container to extend beyond the top edge slightly
            # bottom=5, # Remove bottom constraint
            width=300,  # <-- Increase width of the image container area
            height=300,  # <-- Give it a height too, slightly larger than card text area
            opacity=0.3,  # <-- Set back to semi-transparent
            # expand=True # Optionally expand if needed
            rotate=ft.transform.Rotate(angle=0.2),
            # transform=ft.transform.Scale(scale_x=-1), # <-- Remove transform from container
        )

        # --- Hover effect shadow --- #
        hover_shadow = ft.BoxShadow(
            spread_radius=2,
            blur_radius=15,  # Slightly more blur on hover
            color=ft.colors.with_opacity(0.3, ft.colors.BLACK87),  # Slightly darker shadow
            offset=ft.Offset(2, 4),
        )

        # --- on_hover handler --- #
        def handle_hover(e):
            is_hovering = e.data == "true"
            target_scale = ft.transform.Scale(1.03) if is_hovering else ft.transform.Scale(1.0)
            target_shadow = hover_shadow if is_hovering else card_shadow

            needs_update = False
            # 检查 scale 是否需要更新 (比较 Scale 对象)
            # 注意：直接比较对象可能不准确，取决于 Scale 的 __eq__ 实现
            # 更可靠的方式是比较 scale 属性值，如果 Scale 对象总是存在的话
            current_scale_val = 1.0
            if isinstance(e.control.scale, ft.transform.Scale):
                current_scale_val = e.control.scale.scale if e.control.scale.scale is not None else 1.0
            elif isinstance(e.control.scale, (int, float)):
                 current_scale_val = e.control.scale

            target_scale_val = target_scale.scale if target_scale.scale is not None else 1.0

            if current_scale_val != target_scale_val:
                e.control.scale = target_scale # 重新分配 Scale 对象以触发动画
                needs_update = True

            # 检查 shadow 是否需要更新
            if e.control.shadow != target_shadow:
                 e.control.shadow = target_shadow
                 needs_update = True

            # 如果需要更新，则更新整个页面
            if needs_update and page:
                 print(f"[handle_hover] Updating page due to hover state change: {is_hovering}")
                 page.update() # <--- 修改：更新整个页面
            # else:
                 # print(f"[handle_hover] No update needed for hover state: {is_hovering}")

        return ft.Container(
            # Use Stack to layer text and image
            content=ft.Stack(
                [
                    # Layer 1: Text Content (aligned left implicitly by parent Row settings)
                    # Need to wrap the column in a Row again if we removed the original one,
                    # but let's try putting the column directly first if Stack handles alignment
                    # We need padding inside the stack for the text
                    ft.Container(
                        content=text_content_column,
                        padding=ft.padding.only(top=8, left=15, bottom=15, right=20),  # Apply padding here
                    ),
                    # Layer 2: Emoji Image
                    emoji_image_layer,
                ]
            ),
            height=height,
            width=width,
            border_radius=card_radius,
            # bgcolor=darker_bgcolor,
            bgcolor=card_bgcolor_theme,  # Use theme color
            # Padding is now applied to the inner container for text
            padding=0,
            margin=ft.margin.only(bottom=20),  # Margin applied outside the hover effect
            shadow=card_shadow,
            on_click=on_click_handler,
            tooltip=tooltip,
            ink=True,
            # rotate=ft.transform.Rotate(angle=0.1), # Remove rotate as it might conflict
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # Clip overflowing image within card bounds
            # rotate=ft.transform.Rotate(angle=0.1), # Apply rotation outside hover if needed
            scale=ft.transform.Scale(1.0),  # Initial scale
            animate_scale=ft.animation.Animation(200, "easeOutCubic"),  # Animate scale changes
            on_hover=handle_hover,  # Attach hover handler
        )

    # --- Function to show the tools section (MOVED INSIDE create_main_view) ---
    def show_tools_section(e): # Now has access to page and refs defined above
        # 此函数负责显示工具页面的动画效果，主要完成三个动画：
        # 1. 将背景图片缩小并移动到左下角
        # 2. 将主卡片列向右滑出
        # 3. 显示工具内容卡片
        
        # 1. 将背景形状容器缩小并移动
        if ref_main_button_shape_container.current:
            # target_left = -200
            target_top = -600
            target_scale_val = 0.2 # 缩小到原始大小的25%
            
            # animate_scale和animate_position已在容器初始化时设置
            # Flet动画原理：当控件属性发生变化且设置了对应的animate_*属性时
            # Flet会自动创建从旧值到新值的平滑过渡动画
            ref_main_button_shape_container.current.scale = ft.transform.Scale(target_scale_val)
            # ref_main_button_shape_container.current.left = target_left
            ref_main_button_shape_container.current.top = target_top
            # ref_main_button_shape_container.current.bottom = target_bottom
            # ref_main_button_shape_container.current.top = None  # 设置bottom后需要清除top
            # ref_main_button_shape_container.current.right = None # 设置left后需要清除right
            ref_main_button_shape_container.current.update()

        # 2. 将主卡片列容器向右滑出屏幕
        if ref_main_cards_column_container.current:
            # animate_offset已在容器初始化时设置
            # offset是相对于控件尺寸的偏移量：
            # offset(1.5, 0)表示水平方向右移控件宽度的1.5倍，垂直方向不变
            ref_main_cards_column_container.current.offset = ft.transform.Offset(1.5, 0)
            
            # 定义动画结束后的回调函数
            def on_slide_out_complete(e_anim):
                if ref_main_cards_column_container.current:
                    # 动画完成后将容器设为不可见，优化性能
                    ref_main_cards_column_container.current.visible = False
                    ref_main_cards_column_container.current.update()
            
            # 设置动画结束事件处理器
            # on_animation_end会在offset动画完成后触发
            ref_main_cards_column_container.current.on_animation_end = on_slide_out_complete
            ref_main_cards_column_container.current.update()

        # 3. 显示工具内容卡片
        if ref_active_tool_display_container.current:
            # 0. 清除上一次动画可能设置的 on_animation_end 回调
            ref_active_tool_display_container.current.on_animation_end = None

            # 1. 确保初始状态
            ref_active_tool_display_container.current.visible = True
            ref_active_tool_display_container.current.opacity = 0  # 初始完全透明
            ref_active_tool_display_container.current.update()  # 立即应用初始状态

            # 2. 设置动画属性（使用正确的AnimationCurve常量）
            ref_active_tool_display_container.current.animate_opacity = ft.animation.Animation(
                300,  # 持续时间300ms
                ft.AnimationCurve.EASE_IN  # 使用标准曲线常量
            )
            
            # 3. 触发动画（设置目标值）
            ref_active_tool_display_container.current.opacity = 1
            
            # 4. 更新位置（可选）
            ref_active_tool_display_container.current.alignment = ft.alignment.center_right
            ref_active_tool_display_container.current.right = 60
            ref_active_tool_display_container.current.top = 150
            
            # 5. 更新控件以应用更改并触发动画
            ref_active_tool_display_container.current.update()
        
        # 更新整个页面
        page.update()

    # --- Function to hide the tools section and show main cards ---
    def hide_tools_section(e):
        # 此函数负责隐藏工具页面并返回到主菜单，与show_tools_section执行相反的动画：
        # 1. 淡出并隐藏工具内容卡片
        # 2. 将主卡片列滑回原位
        # 3. 恢复背景图形到原始大小和位置
        
        # 1. 淡出工具内容卡片
        if ref_active_tool_display_container.current:
            # 显式设置动画，使用easeOut曲线
            # "easeOut"与"easeIn"相反，表示动画开始快然后减速
            # 使用不同的曲线可以创造不同的视觉效果和感受
            ref_active_tool_display_container.current.animate_opacity = ft.animation.Animation(300, ft.AnimationCurve.EASE_OUT)
            # 设置目标透明度为0（完全透明）
            ref_active_tool_display_container.current.opacity = 0
            
            # 定义动画结束后的回调函数
            def on_tool_fade_out_complete(e_anim):
                if ref_active_tool_display_container.current:
                    # 动画完成后将卡片设为不可见，避免占用布局空间
                    ref_active_tool_display_container.current.visible = False
                    ref_active_tool_display_container.current.update()
            
            # 设置动画结束事件处理器
            ref_active_tool_display_container.current.on_animation_end = on_tool_fade_out_complete
            ref_active_tool_display_container.current.update()

        # 2. 将主卡片列容器滑回原位
        if ref_main_cards_column_container.current:
            # 先设置为可见，确保在执行动画前能看到它
            ref_main_cards_column_container.current.visible = True
            # animate_offset已在容器初始化时设置
            # 设置offset为(0,0)，即回到原始位置
            ref_main_cards_column_container.current.offset = ft.transform.Offset(0, 0)
            # 清除之前设置的动画结束回调
            ref_main_cards_column_container.current.on_animation_end = None
            ref_main_cards_column_container.current.update()

        # 3. 恢复背景形状容器到原始状态
        if ref_main_button_shape_container.current:
            # animate_scale和animate_position已在容器初始化时设置
            # 恢复到原始缩放比例(1.0)
            ref_main_button_shape_container.current.scale = ft.transform.Scale(1.0)
            # 恢复到原始位置坐标
            ref_main_button_shape_container.current.left = 35
            ref_main_button_shape_container.current.top = -420
            ref_main_button_shape_container.current.bottom = None
            ref_main_button_shape_container.current.right = None
            ref_main_button_shape_container.current.update()
        
        # 更新整个页面，确保所有变化都生效
        page.update()

    # --- Main Button Action --- #
    # Need process_manager for the main button action
    start_bot_card = create_action_card(
        page=page,  # Pass page object
        icon=ft.icons.SMART_TOY_OUTLINED,
        text="主控室",
        subtitle="在此启动 Bot",
        on_click_handler=lambda _: page.go("/console"),
        tooltip="打开 Bot 控制台视图 (在此启动 Bot)",
    )


    # --- Main Column of Cards --- #
    main_cards_column = ft.Column(
        controls=[
            ft.Container(height=15),  # Top spacing
            # Wrap start_bot_card
            ft.Container(
                content=start_bot_card,
                margin=ft.margin.only(top=20, right=10),
                rotate=ft.transform.Rotate(angle=0.12),
            ),
            # --- Move Adapters Card Up --- #
            # Wrap Adapters card
            ft.Container(
                content=create_action_card(
                    page=page,  # Pass page object
                    icon=ft.icons.EXTENSION_OUTLINED,  # Example icon
                    text="适配器",
                    subtitle="管理适配器脚本",
                    on_click_handler=lambda _: page.go("/adapters"),
                    tooltip="管理和运行适配器脚本",
                ),
                margin=ft.margin.only(top=20, right=45),
                rotate=ft.transform.Rotate(angle=0.12),
            ),
            # Re-add the LPMM script card - Now "工具" card
            ft.Container(
                content=create_action_card(
                    page=page,
                    icon=ft.icons.CONSTRUCTION_OUTLINED, # New Icon
                    text="工具",                          # New Text
                    subtitle="所有方便的小工具",          # New Subtitle
                    on_click_handler=show_tools_section, # New Handler for "工具" card
                    tooltip="打开工具区",                # New Tooltip
                ),
                margin=ft.margin.only(top=20, right=15),
                rotate=ft.transform.Rotate(angle=0.12),
            ),
            # more_options_card, # Add the new card with the popup menu (Moved to Stack)
            # --- Add Adapters and Settings Cards --- #
            # Wrap Settings card
            ft.Container(
                content=create_action_card(
                    page=page,  # Pass page object
                    icon=ft.icons.SETTINGS_OUTLINED,  # Example icon
                    text="设置",
                    subtitle="配置所有选项",
                    on_click_handler=lambda _: page.go("/settings"),
                    tooltip="配置启动器选项",
                ),
                margin=ft.margin.only(top=20, right=60),
                rotate=ft.transform.Rotate(angle=0.12),
            ),
        ],
        # alignment=ft.MainAxisAlignment.START, # Default vertical alignment is START
        horizontal_alignment=ft.CrossAxisAlignment.END,  # Align cards to the END (right)
        spacing=0,  # Let card margin handle spacing
        # expand=True, # Remove expand from the inner column if using Stack
        ref=ref_main_cards_column, # Assign ref to the column
    )

    # --- Container for the main_cards_column (this will be animated) ---
    main_cards_column_container_actual = ft.Container(
        content=main_cards_column,
        top=20,
        right=20,
        ref=ref_main_cards_column_container,
        offset=ft.transform.Offset(0,0), # 初始偏移量，无偏移
        animate_offset = ft.animation.Animation(400, "easeOutCubic"), # 初始化时设置偏移动画属性
        # 在Flet中，必须在控件初始化时设置animate_*属性的原因：
        # 1. 确保第一次属性变化时动画能正确触发
        # 2. 如果在属性变化后才设置animate_*，第一次动画可能无法生效
        # 3. animate_offset用于控制offset属性的变化动画
    )

    # --- Container for the "active tool" display ---
    active_tool_card_content = create_action_card(
        page=page,
        icon=ft.icons.FOLDER_SPECIAL_OUTLINED, # Icon for the tools content
        text="LPMM 工具", # Text for the tools content
        subtitle="访问LPMM知识库", # Subtitle for the tools content
        on_click_handler=lambda _: run_script("start_lpmm.bat", page, app_state), # Original action
        tooltip="运行学习脚本 (start_lpmm.bat)"
    )

    # 添加人格生成卡片
    personality_card_content = create_action_card(
        page=page,
        icon=ft.icons.PSYCHOLOGY_OUTLINED,  # 使用心理学图标
        text="人格生成",  # 卡片标题
        subtitle="测试版",  # 副标题
        on_click_handler=lambda _: run_script("start_personality.bat", page, app_state),  # 使用原来的脚本
        tooltip="运行人格生成脚本 (start_personality.bat)"
    )

    # 添加表情包管理卡片到工具区域
    meme_management_card_content = create_action_card(
        page=page,
        icon=ft.icons.EMOJI_EMOTIONS_OUTLINED, 
        text="表情包管理",
        subtitle="查看和管理表情包",
        on_click_handler=lambda _: page.go("/meme-management"), # 点击后跳转到表情包管理视图
        tooltip="打开表情包管理界面"
    )

    tool_view_back_button = ft.ElevatedButton(
        "返回主菜单", 
        on_click=hide_tools_section,
        icon=ft.icons.ARROW_BACK_IOS_NEW_ROUNDED,
        # Style the button as needed
        bgcolor=ft.colors.with_opacity(0.1, ft.colors.ON_SURFACE_VARIANT),
        color=ft.colors.ON_SURFACE_VARIANT
    )

    active_tool_layout = ft.Column(
        [
            active_tool_card_content,  # LPMM工具卡片
            ft.Container(height=20),  # 添加间距
            personality_card_content,  # 人格生成卡片
            ft.Container(height=20),  # 添加间距
            meme_management_card_content, # 表情包管理卡片
            ft.Container(
                content=tool_view_back_button,
                padding=ft.padding.only(top=25, bottom=10),
                alignment=ft.alignment.top_center 
            )
        ],
        alignment=ft.MainAxisAlignment.START,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=10,
    )

    active_tool_display_container_actual = ft.Container(
        content=active_tool_layout, # 包含工具卡片和返回按钮
        width=470, # 容器宽度
        visible=False, # 初始不可见
        opacity=0,     # 初始完全透明
        ref=ref_active_tool_display_container,
        animate_opacity = ft.animation.Animation(300, ft.AnimationCurve.EASE_IN), # 初始化时设置透明度动画
        # Animation对象的参数说明：
        # - 第一个参数：动画持续时间，单位毫秒，这里是300毫秒
        # - 第二个参数：动画曲线，控制动画变化的节奏
        #   - "linear"：匀速变化
        #   - "easeIn"：先慢后快
        #   - "easeOut"：先快后慢
        #   - "easeInOut"：两端慢中间快
        #   - "bounceOut"：有弹跳效果
    )

    return ft.View(
        "/",  # Main view route
        [
            ft.Stack(
                [
                    # --- Giant Orange Stripe (Background) --- #
                    ft.Container(
                        bgcolor=ft.Colors.TERTIARY,  # 使用自定义颜色
                        width=3000,  # Make it very wide
                        height=1000,  # Give it substantial height
                        rotate=ft.transform.Rotate(0.12), 
                        left=-200,
                        top=-500,
                        opacity=1,  # Overall opacity for the stripe
                    ),
                    ft.Container(
                        content=ft.Image(
                            src=get_asset_path("src/MaiGoi/assets/button_shape.png"),  # 使用辅助函数获取正确路径
                            fit=ft.ImageFit.CONTAIN,
                        ),
                        width=900,
                        height=1800,
                        left=35,  # 距离左侧
                        top=-420,  # 距离顶部
                        border_radius=ft.border_radius.all(10),
                        rotate=ft.transform.Rotate(-1.2),
                        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,  # Helps with rounded corners
                        ref=ref_main_button_shape_container, # Assign ref to the image container
                        animate_scale = ft.animation.Animation(400, "easeOutCubic"), # 初始化时设置缩放动画
                        animate_position = ft.animation.Animation(400, "easeOutCubic"), # 初始化时设置位置动画
                        # Flet支持多种动画类型：
                        # 1. animate_opacity：控制透明度变化
                        # 2. animate_scale：控制缩放变化
                        # 3. animate_position：控制位置(left/top/right/bottom)变化
                        # 4. animate_offset：控制偏移(基于控件尺寸的相对位移)
                        # 5. animate_rotation：控制旋转角度变化
                        # 6. animate：容器特有，控制多种属性(尺寸/颜色/边框等)变化
                    ),
                    ft.Container(
                        bgcolor=ft.Colors.TERTIARY,  # 使用自定义颜色
                        width=1000,  # Make it very wide
                        height=1000,  # Give it substantial height
                        rotate=ft.transform.Rotate(0.12), 
                        left=280,
                        top=-561.6,
                        opacity=1,  # Overall opacity for the stripe
                    ),
                    # --- End Giant Orange Stripe ---
                    ft.Container(
                        bgcolor=ft.Colors.SECONDARY,  # 使用自定义颜色
                        width=800,  # Make it very wide
                        height=3000,  # Give it substantial height
                        rotate=ft.transform.Rotate(0.6),  
                        left=-500,
                        top=-1600,
                        opacity=1,  # Overall opacity for the stripe
                    ),
                    main_cards_column_container_actual, # Use the new container for main cards
                    # --- Add the active tool display container to the stack ---
                    active_tool_display_container_actual, # Add it here
                    # --- Add Large Text to Bottom Left ---
                    ft.Container(
                        content=ft.Text(
                            "MAI",
                            size=50,
                            font_family="Microsoft YaHei",
                            weight=ft.FontWeight.W_700,
                            color=ft.colors.with_opacity(1, ft.colors.WHITE10),
                        ),
                        left=32,
                        top=30,
                        rotate=ft.transform.Rotate(-0.98),
                    ),
                    ft.Container(
                        content=ft.Text(
                            "工具箱",
                            size=80,
                            font_family="Microsoft YaHei",  # 使用相同的锐利字体
                            weight=ft.FontWeight.W_700,  # 加粗
                            color=ft.colors.with_opacity(1, ft.colors.WHITE10),
                        ),
                        left=-10,
                        top=78,
                        rotate=ft.transform.Rotate(-0.98),
                    ),
                    # --- End Add Large Text ---
                ],
                expand=True,  # Make Stack fill the available space
            ),
        ],
        bgcolor=ft.Colors.INVERSE_SURFACE,  # 使用自定义颜色
    )


# --- Adapters View --- #
def create_adapters_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """Creates the view for managing adapters (/adapters)."""
    # Import necessary functions
    from .config_manager import save_config
    from .utils import show_snackbar  # Removed run_script import

    # Import process management functions
    from .process_manager import start_managed_process, stop_managed_process
    import psutil  # To check if PID exists for status

    adapters_list_view = ft.ListView(expand=True, spacing=5)

    def update_adapters_list():
        """Refreshes the list view with current adapter paths and status-dependent buttons."""
        adapters_list_view.controls.clear()
        for index, path in enumerate(app_state.adapter_paths):
            # 使用与start_adapter_process相同的进程ID生成逻辑
            display_name = os.path.basename(path)
            process_id = f"adapter_{display_name.replace('.', '_')}"
            
            # 检查进程状态
            process_state = app_state.managed_processes.get(process_id)
            is_running = False
            if (
                process_state
                and process_state.status == "running"
                and process_state.pid
                and psutil.pid_exists(process_state.pid)
            ):
                is_running = True

            action_buttons = []
            if is_running:
                # If running: View Output Button and Stop Button
                action_buttons.append(
                    ft.IconButton(
                        ft.icons.VISIBILITY_OUTLINED,
                        tooltip="查看输出",
                        data=process_id,  # 使用进程ID而非路径
                        on_click=lambda e: page.go(f"/adapters/{e.control.data}"),
                        icon_color=ft.colors.BLUE_GREY,  # Neutral color
                    )
                )
                action_buttons.append(
                    ft.IconButton(
                        ft.icons.STOP_CIRCLE_OUTLINED,
                        tooltip="停止此适配器",
                        data=process_id,  # 使用进程ID而非路径
                        # Call stop and then refresh the list view
                        on_click=lambda e: (
                            stop_managed_process(e.control.data, page, app_state),
                            update_adapters_list(),
                        ),
                        icon_color=ft.colors.RED_ACCENT,
                    )
                )
            else:
                # If stopped: Start Button
                action_buttons.append(
                    ft.IconButton(
                        ft.icons.PLAY_ARROW_OUTLINED,
                        tooltip="启动此适配器脚本",
                        data=path,  # 仍然需要传递路径以便正确启动
                        on_click=lambda e: start_adapter_process(e, page, app_state),
                        icon_color=ft.colors.GREEN,
                    )
                )

            adapters_list_view.controls.append(
                ft.Row(
                    [
                        ft.Text(path, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                        # Add action buttons based on state
                        *action_buttons,
                        # Keep the remove button
                        ft.IconButton(
                            ft.icons.DELETE_OUTLINE,
                            tooltip="移除此适配器",
                            data=index,  # Store index to know which one to remove
                            on_click=remove_adapter,
                            icon_color=ft.colors.ERROR,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                )
            )
        
        # 安全地更新UI - 添加判断确保控件已添加到页面
        print("[Adapters] 更新适配器列表，当前适配器数量:", len(app_state.adapter_paths))
        try:
            # 检查控件是否已添加到页面
            if adapters_list_view.page:
                adapters_list_view.update()
            else:
                print("[Adapters] 列表视图尚未添加到页面，跳过update调用")
        except Exception as e:
            print(f"[Adapters] 更新列表视图时出错: {e}")

    def remove_adapter(e):
        """Removes an adapter path based on the button's data (index)."""
        index_to_remove = e.control.data
        if 0 <= index_to_remove < len(app_state.adapter_paths):
            removed_path = app_state.adapter_paths.pop(index_to_remove)
            app_state.gui_config["adapters"] = app_state.adapter_paths
            
            print(f"[Adapters] 准备移除适配器: {removed_path}")
            print(f"[Adapters] 移除后的适配器列表: {app_state.adapter_paths}")
            
            if save_config(app_state.gui_config, base_dir=app_state.bot_base_dir):
                # 验证配置一致性
                from .config_manager import verify_config_consistency
                results = verify_config_consistency()
                print("[Adapters] 移除后配置一致性验证结果:")
                for name, path, exists in results:
                    print(f"  - {name}: {path} ({'存在' if exists else '不存在'})")
                
                # 立即更新列表视图
                update_adapters_list()
                show_snackbar(page, f"已移除: {removed_path}")
            else:
                show_snackbar(page, "保存配置失败，未能移除", error=True)
                # Revert state
                app_state.adapter_paths.insert(index_to_remove, removed_path)
                app_state.gui_config["adapters"] = app_state.adapter_paths
        else:
            show_snackbar(page, "移除时发生错误：无效索引", error=True)

    # --- Start Adapter Process Handler --- #
    def start_adapter_process(e, page: ft.Page, app_state: "AppState"):
        """Handles the click event for the start adapter button."""
        path_to_run = e.control.data
        if not path_to_run or not isinstance(path_to_run, str):
            show_snackbar(page, "运行错误：无效的适配器路径", error=True)
            return

        display_name = os.path.basename(path_to_run)  # Use filename as display name
        
        # 使用安全的进程ID - 使用文件名作为ID而不是完整路径
        # 这样可以避免URL中的特殊字符问题
        process_id = f"adapter_{display_name.replace('.', '_')}"
        
        # print(f"[Adapters View] 请求启动: {display_name} (ID: {process_id})")

        # Call the generic start function from process_manager
        # It will create the specific ListView in the state
        success, message = start_managed_process(
            script_path=path_to_run,
            type="adapter",
            display_name=display_name,
            page=page,
            app_state=app_state,
            process_id=process_id,  # 传递生成的进程ID
        )

        if success:
            show_snackbar(page, f"正在启动: {display_name}")
            update_adapters_list()  # Refresh button states
            # Navigate to the specific output view for this process
            page.go(f"/adapters/{process_id}")
        else:
            # Error message already shown by start_managed_process via snackbar
            update_adapters_list()  # Refresh button states even on failure

    # --- Initial population of the list --- #
    update_adapters_list()

    new_adapter_path_field = ft.TextField(label="新适配器路径 (.py 文件)", expand=True)

    # --- File Picker Logic --- #
    def pick_adapter_file_result(e: ft.FilePickerResultEvent):
        """Callback when the file picker dialog closes."""
        if e.files:
            selected_file = e.files[0]  # Get the first selected file
            new_adapter_path_field.value = selected_file.path
            new_adapter_path_field.update()
            show_snackbar(page, f"已选择文件: {os.path.basename(selected_file.path)}")
        else:
            show_snackbar(page, "未选择文件")

    def open_file_picker(e):
        """Opens the file picker dialog."""
        if app_state.file_picker:
            app_state.file_picker.on_result = pick_adapter_file_result
            app_state.file_picker.pick_files(
                allow_multiple=False,
                allowed_extensions=["py"],  # Only allow Python files
                dialog_title="选择适配器 Python 文件",
            )
        else:
            show_snackbar(page, "错误：无法打开文件选择器", error=True)

    # Ensure the file picker's on_result is connected when the view is created
    if app_state.file_picker:
        app_state.file_picker.on_result = pick_adapter_file_result
    else:
        # This case shouldn't happen if main.py runs correctly
        print("[create_adapters_view] Warning: FilePicker not available during view creation.")

    def add_adapter(e):
        """Adds a new adapter path to the list and config."""
        new_path = new_adapter_path_field.value.strip()

        if not new_path:
            show_snackbar(page, "请输入适配器路径", error=True)
            return
        # Basic validation (you might want more robust checks)
        if not new_path.lower().endswith(".py"):
            show_snackbar(page, "路径应指向一个 Python (.py) 文件", error=True)
            return
        # Optional: Check if the file actually exists? Might be too strict.
        # if not os.path.exists(new_path):
        #     show_snackbar(page, f"文件未找到: {new_path}", error=True)
        #     return

        if new_path in app_state.adapter_paths:
            show_snackbar(page, "此适配器路径已存在")
            return

        # 添加调试信息
        print(f"[Adapters] 当前适配器列表: {app_state.adapter_paths}")
        print(f"[Adapters] 准备添加新路径: {new_path}")
        print(f"[Adapters] bot_base_dir: {app_state.bot_base_dir}")

        app_state.adapter_paths.append(new_path)
        app_state.gui_config["adapters"] = app_state.adapter_paths

        # 添加更多调试信息
        print(f"[Adapters] 添加后适配器列表: {app_state.adapter_paths}")
        print(f"[Adapters] 准备保存配置，gui_config['adapters']: {app_state.gui_config['adapters']}")

        save_successful = save_config(app_state.gui_config, base_dir=app_state.bot_base_dir)

        print(f"[Adapters] 保存配置结果: {'成功' if save_successful else '失败'}")
        
        # 验证配置一致性
        from .config_manager import verify_config_consistency
        results = verify_config_consistency()
        print("[Adapters] 保存后配置一致性验证结果:")
        for name, path, exists in results:
            print(f"  - {name}: {path} ({'存在' if exists else '不存在'})")

        if save_successful:
            new_adapter_path_field.value = ""  # Clear input field
            # 立即更新列表视图
            update_adapters_list()
            new_adapter_path_field.update()  # Update the input field visually
            show_snackbar(page, "适配器已添加")
        else:
            show_snackbar(page, "保存配置失败", error=True)
            # Revert state if save failed
            try:  # Add try-except just in case pop fails unexpectedly
                app_state.adapter_paths.pop()
                app_state.gui_config["adapters"] = app_state.adapter_paths
            except IndexError:
                pass  # Silently ignore if list was empty during failed save

    return ft.View(
        "/adapters",
        [
            ft.AppBar(title=ft.Text("适配器管理"), bgcolor=ft.colors.SURFACE_VARIANT),
            # Use a Container with the padding property instead
            ft.Container(
                padding=ft.padding.all(10),  # Set padding property on the Container
                content=ft.Column(  # Place the original content inside the Container
                    [
                        ft.Text("已配置的适配器:"),
                        adapters_list_view,  # ListView for adapters
                        ft.Divider(),
                        ft.Row(
                            [
                                new_adapter_path_field,
                                # --- Add Browse Button --- #
                                ft.IconButton(
                                    ft.icons.FOLDER_OPEN_OUTLINED,
                                    tooltip="浏览文件...",
                                    on_click=open_file_picker,  # Call the file picker opener
                                ),
                                ft.IconButton(ft.icons.ADD_CIRCLE_OUTLINE, tooltip="添加适配器", on_click=add_adapter),
                            ]
                        ),
                    ],
                    expand=True,
                ),
            ),
        ],
    )


# --- Settings View --- #
def create_settings_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """Placeholder for settings view."""
    # This function is now implemented in ui_settings_view.py
    # This placeholder can be removed if no longer referenced anywhere else.
    # For safety, let's keep it but make it clear it's deprecated/moved.
    print("Warning: Deprecated create_settings_view called in ui_views.py. Should use ui_settings_view.py version.")
    return ft.View(
        "/settings_deprecated",
        [ft.AppBar(title=ft.Text("Settings (Deprecated)")), ft.Text("This view has moved to ui_settings_view.py")],
    )


# --- Process Output View (for Adapters etc.) --- #
def create_process_output_view(page: ft.Page, app_state: "AppState", process_id: str) -> Optional[ft.View]:
    """Creates a view to display the output of a specific managed process."""
    # Import stop function
    from .process_manager import stop_managed_process

    print(f"[Create Output View] 构建适配器输出视图: {process_id}")

    # 定义自定义返回函数
    def handle_back_button(_):
        page.go("/adapters")  # 返回适配器列表页面

    process_state = app_state.managed_processes.get(process_id)
    if not process_state:
        print(f"[Create Output View] 错误: 未找到进程状态: ID={process_id}")
        
        # 尝试找到适配器路径，通过process_id反向查找
        adapter_path = None
        display_name = None
        if process_id.startswith("adapter_"):
            base_name = process_id[8:].replace('_', '.') # 移除"adapter_"前缀并恢复文件扩展名
            for path in app_state.adapter_paths:
                if os.path.basename(path) == base_name:
                    adapter_path = path
                    display_name = base_name
                    break
        
        if adapter_path:
            print(f"[Create Output View] 找到适配器路径: {adapter_path}，创建临时视图")
            
            # 创建一个临时ListView
            temp_output_lv = ft.ListView(expand=True, spacing=2, padding=5, auto_scroll=True)
            temp_output_lv.controls.append(
                ft.Text(
                    f"--- 适配器 {display_name} 当前未运行或已停止 ---",
                    italic=True,
                    color=ft.colors.BLUE_GREY,
                )
            )
            
            # 创建启动按钮
            start_button = ft.ElevatedButton(
                "启动适配器",
                icon=ft.icons.PLAY_ARROW,
                on_click=lambda _: start_adapter_from_view(adapter_path, page, app_state),
                bgcolor=ft.colors.with_opacity(0.6, ft.colors.GREEN_ACCENT_100),
                color=ft.colors.WHITE,
            )
            
            # 返回临时视图，添加自定义返回处理
            return ft.View(
                route=f"/adapters/{process_id}",
                appbar=ft.AppBar(
                    title=ft.Text(f"输出: {display_name} (未运行)"),
                    bgcolor=ft.colors.SURFACE_VARIANT,
                    leading=ft.IconButton(icon=ft.icons.ARROW_BACK, on_click=handle_back_button),
                    leading_width=40,
                    automatically_imply_leading=False,
                    actions=[
                        start_button,
                        ft.Container(width=5),
                    ],
                ),
                controls=[temp_output_lv],
                padding=0,
            )
        
        # 如果无法找到匹配的适配器路径，返回None
        return None

    # Get or create the ListView for this process
    # It should have been created and stored by start_managed_process
    if process_state.output_list_view is None:
        print(f"[Create Output View] 警告: {process_id} 没有输出视图，创建新视图")
        # Create a fallback, though this indicates an issue elsewhere
        process_state.output_list_view = ft.ListView(expand=True, spacing=2, padding=5, auto_scroll=True)
        
        status_text = "已停止"
        status_color = ft.colors.BLUE_GREY
        if process_state.status == "running" and process_state.pid and psutil.pid_exists(process_state.pid):
            status_text = "正在运行中"
            status_color = ft.colors.GREEN
        
        process_state.output_list_view.controls.append(
            ft.Text(
                f"--- 适配器状态: {status_text} ---",
                italic=True,
                color=status_color,
            )
        )

    output_lv = process_state.output_list_view

    # --- AppBar reference --- #
    app_bar_title_ref = ft.Ref[ft.Text]()

    # --- Button Actions & UI Update Logic --- #
    def _update_app_bar_and_buttons(current_page: ft.Page, current_app_bar: ft.AppBar):
        # Re-fetch the latest process state
        latest_process_state = app_state.managed_processes.get(process_id)
        if not latest_process_state:
            # This case should ideally not happen if process_id is valid
            print(f"[Adapter View Update] Warning: process_state for {process_id} not found during update.")
            return

        is_now_running = latest_process_state.status == "running" and latest_process_state.pid and psutil.pid_exists(latest_process_state.pid)
        new_status_text = "运行中" if is_now_running else "已停止"
        
        # Update AppBar Title
        if app_bar_title_ref.current:
            app_bar_title_ref.current.value = f"输出: {latest_process_state.display_name} ({new_status_text})"

        # Create new action button based on current state
        new_action_button = None
        if is_now_running:
            new_action_button = ft.ElevatedButton(
                "停止进程",
                icon=ft.icons.STOP_CIRCLE_OUTLINED,
                on_click=do_stop_and_refresh, 
                bgcolor=ft.colors.with_opacity(0.6, ft.colors.RED_ACCENT_100),
                color=ft.colors.WHITE,
                tooltip=f"停止 {latest_process_state.display_name}",
            )
        else:
            new_action_button = ft.ElevatedButton(
                "重新启动",
                icon=ft.icons.PLAY_ARROW,
                on_click=do_start_and_refresh, 
                bgcolor=ft.colors.with_opacity(0.6, ft.colors.GREEN_ACCENT_100),
                color=ft.colors.WHITE,
                tooltip=f"重新启动 {latest_process_state.display_name}",
            )
        
        # The AppBar's `actions` list is [action_button, auto_scroll_button, ft.Container(width=5)]
        # We only need to replace the action_button (at index 0).
        current_actions = list(current_app_bar.actions) 
        if current_actions: # Should always be true if initialized correctly
            current_actions[0] = new_action_button 
            current_app_bar.actions = current_actions
        else:
            # Fallback, though this indicates an issue with initial AppBar setup
            current_app_bar.actions = [new_action_button, ft.Container(width=5)]

        current_app_bar.update()

    # Button click handlers
    def do_stop_and_refresh(_):
        stop_managed_process(process_id, page, app_state)
        _update_app_bar_and_buttons(page, view_app_bar)

    def do_start_and_refresh(_):
        start_adapter_from_view(process_state.script_path, page, app_state, process_id)
        _update_app_bar_and_buttons(page, view_app_bar)

    # Determine initial state for button creation
    is_running = process_state.status == "running" and process_state.pid and psutil.pid_exists(process_state.pid)
    initial_status_text = "运行中" if is_running else "已停止"
    
    action_button = None
    if is_running:
        action_button = ft.ElevatedButton(
            "停止进程",
            icon=ft.icons.STOP_CIRCLE_OUTLINED,
            on_click=do_stop_and_refresh, 
            bgcolor=ft.colors.with_opacity(0.6, ft.colors.RED_ACCENT_100),
            color=ft.colors.WHITE,
            tooltip=f"停止 {process_state.display_name}",
        )
    else:
        action_button = ft.ElevatedButton(
            "重新启动",
            icon=ft.icons.PLAY_ARROW,
            on_click=do_start_and_refresh, 
            bgcolor=ft.colors.with_opacity(0.6, ft.colors.GREEN_ACCENT_100),
            color=ft.colors.WHITE,
            tooltip=f"重新启动 {process_state.display_name}",
        )

    # --- Auto-scroll Toggle (Specific to this view) --- #
    is_this_view_auto_scroll = ft.Ref[bool]()
    is_this_view_auto_scroll.current = True 
    output_lv.auto_scroll = is_this_view_auto_scroll.current

    def toggle_this_view_auto_scroll(e):
        is_this_view_auto_scroll.current = not is_this_view_auto_scroll.current
        output_lv.auto_scroll = is_this_view_auto_scroll.current
        e.control.text = "自动滚动 开" if is_this_view_auto_scroll.current else "自动滚动 关"
        e.control.update()
        print(f"Process '{process_id}' view auto-scroll set to: {is_this_view_auto_scroll.current}")

    auto_scroll_button = ft.OutlinedButton(
        "自动滚动 开" if is_this_view_auto_scroll.current else "自动滚动 关",
        icon=ft.icons.SWAP_VERT, 
        on_click=toggle_this_view_auto_scroll,
        tooltip="切换此视图的自动滚动",
    )
    
    button_list_for_appbar = [action_button, auto_scroll_button, ft.Container(width=5)]

    # Create the AppBar instance here so we can pass it to the update function
    view_app_bar = ft.AppBar(
            ref=ft.Ref[ft.AppBar](), # Optional: give AppBar a ref if needed elsewhere
            title=ft.Text(f"输出: {process_state.display_name} ({initial_status_text})", ref=app_bar_title_ref),
            bgcolor=ft.colors.SURFACE_VARIANT,
            leading=ft.IconButton(icon=ft.icons.ARROW_BACK, on_click=handle_back_button),
            leading_width=40,
            automatically_imply_leading=False,
            actions=button_list_for_appbar,
        )

    return ft.View(
        route=f"/adapters/{process_id}",
        appbar=view_app_bar, # Use the created AppBar instance
        controls=[
            output_lv 
        ],
        padding=0,
    )

# --- 辅助函数 ---
def start_adapter_from_view(script_path, page, app_state, existing_process_id=None):
    """从详情视图中启动适配器"""
    # 导入依赖函数
    from .process_manager import start_managed_process
    from .utils import show_snackbar
    
    display_name = os.path.basename(script_path)
    process_id = existing_process_id
    if not process_id:
        process_id = f"adapter_{display_name.replace('.', '_')}"
    
    print(f"[启动适配器] 从视图启动: {script_path}, process_id={process_id}")
    
    # 调用启动函数
    success, message = start_managed_process(
        script_path=script_path,
        type="adapter",
        display_name=display_name,
        page=page,
        app_state=app_state,
        process_id=process_id,
    )
    
    if success:
        show_snackbar(page, f"已启动: {display_name}")
        # 刷新视图
        page.go(f"/adapters/{process_id}")
    else:
        show_snackbar(page, message, error=True)


# --- Meme Management View --- #
def create_meme_management_view(page: ft.Page, app_state: "AppState") -> ft.View:
    """Creates the view for managing memes (/meme-management).
       Uses the meme_manager to build the actual grid of memes.
    """
    
    # The main content is now built by meme_manager
    meme_grid_content = build_meme_grid(page, app_state)

    return ft.View(
        "/meme-management",
        [
            ft.AppBar(title=ft.Text("表情包管理"), bgcolor=ft.colors.SURFACE_VARIANT),
            meme_grid_content, # <-- Use the content from meme_manager
        ],
        padding=0
    )
