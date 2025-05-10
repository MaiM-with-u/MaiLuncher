import flet as ft
import tomlkit
from pathlib import Path
import webbrowser  # 添加导入webbrowser模块用于打开网页
from typing import Dict, Any

from .state import AppState
from .utils import show_snackbar  # Assuming show_snackbar is in utils
from .toml_form_generator import create_toml_form, load_bot_config, get_bot_config_path
from .config_manager import load_config, save_config
from .ui_env_editor import create_env_editor_page_content, load_env_data
from .db_connector import full_database_reset # 修改导入
from .mmc_downloader import show_mmc_downloader  # 添加导入新模块

# 添加一个全局变量来标记是否需要刷新配置
CONFIG_NEEDS_REFRESH = False

def save_bot_config(page: ft.Page, app_state: AppState, new_config_data: dict):
    """将修改后的 Bot 配置保存回文件。"""
    config_path = get_bot_config_path(app_state)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            # Use tomlkit.dumps to preserve formatting/comments as much as possible
            # It might need refinement based on how UI controls update the dict
            tomlkit.dump(new_config_data, f)
        show_snackbar(page, "Bot 配置已保存！")
        # Optionally reload config into app_state if needed immediately elsewhere
        # app_state.bot_config = new_config_data # Or reload using a dedicated function
    except Exception as e:
        print(f"Error saving bot config: {e}")
        show_snackbar(page, f"保存 Bot 配置失败: {e}", error=True)


def save_bot_config_changes(page: ft.Page, config_to_save: dict, app_state: AppState, silent: bool = False):
    """Handles saving changes for bot_config.toml"""
    if not silent:
        print("[Settings] Saving Bot Config (TOML) changes...")
    # Assuming save_config needs path, let's build it or adapt save_config
    # For now, let's assume save_config can handle type='bot'
    # config_path = get_bot_config_path(app_state) # Need app_state if using this
    success = save_config(config_to_save, config_type="bot", base_dir=app_state.bot_base_dir)
    if not silent:
        if success:
            message = "Bot 配置已保存！"
        else:
            message = "保存 Bot 配置失败。"
        show_snackbar(page, message, error=(not success))
    elif not success:
        print("[Settings] Error during silent save of Bot Config.")


def save_lpmm_config_changes(page: ft.Page, config_to_save: dict, app_state: AppState, silent: bool = False):
    """Handles saving changes for lpmm_config.toml"""
    if not silent:
        print("[Settings] Saving LPMM Config (TOML) changes...")
    success = save_config(config_to_save, config_type="lpmm", base_dir=app_state.bot_base_dir)
    if not silent:
        if success:
            message = "LPMM 配置已保存！"
        else:
            message = "保存 LPMM 配置失败。"
        show_snackbar(page, message, error=(not success))
    elif not success:
        print("[Settings] Error during silent save of LPMM Config.")


def save_gui_config_changes(page: ft.Page, app_state: AppState, silent: bool = False):
    """Handles saving changes for gui_config.toml"""
    if not silent: # Only print if not silent
        print("[Settings] Saving GUI Config changes...")
    # gui_config is directly in app_state, no need to pass config_to_save
    success = save_config(app_state.gui_config, config_type="gui", base_dir=app_state.bot_base_dir)
    if not silent: # Only show snackbar if not silent
        if success:
            message = "GUI 配置已保存！"
        else:
            message = "保存 GUI 配置失败。"
        show_snackbar(page, message, error=(not success))
    elif not success: # Still log error even if silent
        print("[Settings] Error during silent save of GUI Config.")


def load_config_metadata(app_state: AppState) -> dict:
    """加载配置元数据文件"""
    try:
        # 获取bot.py所在目录
        bot_dir = Path(app_state.mmc_path)
        meta_path = bot_dir / "template" / "bot_config_meta.toml"
        
        print(f"[Settings] 尝试加载元数据文件: {meta_path}")
        
        if not meta_path.exists():
            print(f"[Settings] 警告: 未找到配置元数据文件: {meta_path}")
            return {}
            
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = tomlkit.load(f)
            print(f"[Settings] 成功加载配置元数据文件，包含 {len(metadata)} 个顶级键")
            return metadata
    except Exception as e:
        print(f"[Settings] 加载配置元数据文件时出错: {e}")
        import traceback
        traceback.print_exc()
        return {}


def create_important_settings_card(page: ft.Page, config_data: Dict[str, Any], config_metadata: Dict[str, Any]) -> ft.Card:
    """创建重要设置卡片"""
    important_items = []
    print(f"[Settings] 开始创建重要设置卡片，配置数据: {config_data}")
    print(f"[Settings] 元数据: {config_metadata}")
    
    def get_metadata_for_path(path: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """递归查找路径对应的元数据"""
        parts = path.split(".")
        current = metadata
        
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part, {})
            else:
                return {}
                
        return current if isinstance(current, dict) else {}
    
    def process_section(section_data: Dict[str, Any], section_path: str = ""):
        """递归处理配置部分，收集重要项"""
        for key, value in section_data.items():
            full_path = f"{section_path}.{key}" if section_path else key
            print(f"[Settings] 处理配置项: {full_path}")
            
            # 获取元数据
            metadata = get_metadata_for_path(full_path, config_metadata)
            print(f"[Settings] 项 {full_path} 的元数据: {metadata}")
            
            # 检查当前项是否重要
            is_important = metadata.get("important", False)
            if is_important:
                print(f"[Settings] 找到重要项: {full_path}")
                # 获取描述
                describe = metadata.get("describe", "")
                # 创建控件
                if isinstance(value, bool):
                    control = ft.Switch(
                        label=key,
                        value=value,
                        disabled=not metadata.get("can_edit", True),
                    )
                elif isinstance(value, (int, float)):
                    control = ft.TextField(
                        label=key,
                        value=str(value),
                        disabled=not metadata.get("can_edit", True),
                    )
                elif isinstance(value, str):
                    control = ft.TextField(
                        label=key,
                        value=value,
                        disabled=not metadata.get("can_edit", True),
                    )
                elif isinstance(value, list):
                    # 对于列表类型，显示为逗号分隔的字符串
                    control = ft.TextField(
                        label=key,
                        value=", ".join(str(x) for x in value),
                        disabled=not metadata.get("can_edit", True),
                    )
                else:
                    print(f"[Settings] 跳过复杂类型: {full_path}")
                    continue  # 跳过复杂类型
                
                # 添加描述文本
                important_items.append(
                    ft.Column([
                        control,
                        ft.Text(describe, size=12, color=ft.colors.SECONDARY),
                        ft.Divider()
                    ])
                )
            
            # 递归处理子部分
            if isinstance(value, dict):
                process_section(value, full_path)
    
    # 处理配置数据
    process_section(config_data)
    print(f"[Settings] 找到 {len(important_items)} 个重要项")
    
    # 如果没有重要项，返回空卡片
    if not important_items:
        print("[Settings] 没有找到重要项，返回空卡片")
        return ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("没有重要设置项", italic=True)
                ]),
                padding=10
            )
        )
    
    # 创建重要设置卡片
    print("[Settings] 创建重要设置卡片")
    return ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Text("重要设置", weight=ft.FontWeight.BOLD, size=16),
                ft.Divider(),
                *important_items
            ]),
            padding=10
        ),
        margin=ft.margin.only(bottom=10)
    )


def create_settings_view(page: ft.Page, app_state: AppState) -> ft.View:
    """Creates the settings view with sections for different config files."""

    # --- State for switching between editors ---
    content_area = ft.Column([], expand=True, scroll=ft.ScrollMode.ADAPTIVE)
    current_config_data = {}  # Store loaded data for saving
    
    # --- 添加下载MMC和安装Python按钮函数 --- #
    def download_mmc(e):
        # 使用新的MMC下载器替代简单的网页打开
        show_mmc_downloader(page)
        
    def install_python(e):
        # 改为直接在当前窗口中显示Python安装助手对话框
        try:
            # 导入Python安装器模块
            from .python_installer import show_python_installer
            
            # 直接在当前页面显示Python安装器对话框
            show_python_installer(page)
            
        except Exception as ex:
            show_snackbar(page, f"启动Python安装助手失败: {str(ex)}", error=True)
            import traceback
            traceback.print_exc()

    # --- Function to load Bot config editor (Original TOML editor) ---
    def show_bot_config_editor(e=None):
        global CONFIG_NEEDS_REFRESH
        nonlocal current_config_data
        print("[Settings] Loading Bot Config Editor")
        try:
            # 检查是否需要强制刷新
            if CONFIG_NEEDS_REFRESH:
                print("[Settings] 检测到配置变更，强制重新加载")
                # 确保使用最新的 app_state.bot_base_dir
                current_bot_config = load_config(config_type="bot", base_dir=app_state.bot_base_dir)
                CONFIG_NEEDS_REFRESH = False  # 重置标记
            else:
                current_bot_config = load_config(config_type="bot", base_dir=app_state.bot_base_dir)
            
            if not current_bot_config:
                if not app_state.bot_base_dir:
                    raise ValueError("Bot base directory is not set. Cannot load bot config.")
                
                # 尝试多种编码方式读取文件
                config_path = app_state.bot_base_dir / 'config' / 'bot_config.toml'
                encodings_to_try = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin-1']
                config_content = None
                
                print(f"[Settings] 尝试以多种编码读取配置文件: {config_path}")
                for encoding in encodings_to_try:
                    try:
                        with open(config_path, 'r', encoding=encoding) as f:
                            config_content = f.read()
                        print(f"[Settings] 成功使用编码 {encoding} 读取文件")
                        # 尝试解析TOML
                        try:
                            parsed_config = tomlkit.parse(config_content)
                            print(f"[Settings] 成功使用编码 {encoding} 解析TOML")
                            current_bot_config = parsed_config
                            break
                        except Exception as parse_err:
                            print(f"[Settings] 使用编码 {encoding} 解析TOML失败: {parse_err}")
                            continue
                    except Exception as read_err:
                        print(f"[Settings] 使用编码 {encoding} 读取文件失败: {read_err}")
                        continue
                
                if not current_bot_config:
                    # 如果所有编码都失败，则显示错误
                    raise ValueError(f"尝试多种编码均无法加载配置文件: {config_path}")
            
            current_config_data = current_bot_config # Keep reference if needed elsewhere
            content_area.controls.clear()

            # 加载配置元数据
            config_metadata = load_config_metadata(app_state)
            print(f"[Settings] 加载的元数据: {config_metadata}")

            # Define the save callback for the bot config
            def bot_save_callback(data_to_save):
                return save_bot_config_changes(page, data_to_save, app_state, silent=True)

            # 创建一个临时容器来存放表单控件
            form_container = ft.Column([], expand=True, scroll=ft.ScrollMode.AUTO)
            
            # Pass the callback and metadata to the form generator
            form_generator = create_toml_form(
                page,
                current_bot_config, # Pass the data directly
                form_container,
                template_filename="bot_config_template.toml",
                save_callback=bot_save_callback,
                debounce_interval=1.5, # Optional: slightly longer debounce
                config_metadata=config_metadata # 传递元数据
            )
            
            # 先创建重要设置卡片
            important_card = create_important_settings_card(page, current_bot_config, config_metadata)
            
            # 将重要设置卡片和表单添加到内容区域
            if important_card:
                print("[Settings] 添加重要设置卡片到内容区域")
                content_area.controls.append(important_card)
                # 添加一个分隔线
                content_area.controls.append(ft.Divider())
                # 添加一个标题
                content_area.controls.append(
                    ft.Text("完整配置", weight=ft.FontWeight.BOLD, size=16)
                )
                content_area.controls.append(ft.Divider())
            
            # 将表单控件添加到内容区域
            content_area.controls.append(form_container)
            
            # 强制更新页面
            if page:
                page.update()
                print("[Settings] 页面已更新")
        except Exception as ex:
            content_area.controls.clear()
            content_area.controls.append(ft.Text(f"加载 Bot 配置时出错: {ex}", color=ft.colors.ERROR))
            import traceback
            traceback.print_exc()
        if page:
            page.update()

    # --- Function to load LPMM config editor ---
    def show_lpmm_editor(e=None):
        global CONFIG_NEEDS_REFRESH
        nonlocal current_config_data
        print("[Settings] Loading LPMM Config Editor")
        try:
            # 检查是否需要强制刷新
            if CONFIG_NEEDS_REFRESH:
                print("[Settings] 检测到配置变更，强制重新加载")
                # 确保使用最新的 app_state.bot_base_dir
                lpmm_config = load_config(config_type="lpmm", base_dir=app_state.bot_base_dir)
                CONFIG_NEEDS_REFRESH = False  # 重置标记
            else:
                lpmm_config = load_config(config_type="lpmm", base_dir=app_state.bot_base_dir)
            
            if not lpmm_config:
                if not app_state.bot_base_dir:
                    raise ValueError("Bot base directory is not set. Cannot load LPMM config.")
                raise ValueError(f"LPMM config could not be loaded from {app_state.bot_base_dir / 'config' / 'lpmm_config.toml'}.")
            current_config_data = lpmm_config # Keep reference
            content_area.controls.clear()

            # Define the save callback for LPMM config
            def lpmm_save_callback(data_to_save):
                return save_lpmm_config_changes(page, data_to_save, app_state, silent=True)

            # Pass the callback to the form generator
            form_generator = create_toml_form(
                page,
                lpmm_config, # Pass the data directly
                content_area,
                template_filename="lpmm_config_template.toml",
                save_callback=lpmm_save_callback,
                debounce_interval=1.5 # Optional: slightly longer debounce
            )
            # No explicit save button needed anymore
            # save_button = ft.ElevatedButton(...)
            # content_area.controls.append(ft.Divider())
            # content_area.controls.append(save_button)
        except Exception as ex:
            content_area.controls.clear()
            content_area.controls.append(ft.Text(f"加载 LPMM 配置时出错: {ex}", color=ft.colors.ERROR))
        if page:
            page.update()

    # --- Function to load .env editor ---
    def show_env_editor(e=None):
        global CONFIG_NEEDS_REFRESH
        # No config data to manage here, it handles its own save
        print("[Settings] Loading .env Editor")
        
        if CONFIG_NEEDS_REFRESH:
            print("[Settings] 检测到配置变更，强制重新加载 .env 编辑器")
            CONFIG_NEEDS_REFRESH = False  # 重置标记
        
        content_area.controls.clear()
        env_editor_content = create_env_editor_page_content(page, app_state)
        content_area.controls.append(env_editor_content)
        if page:
            page.update()

    # --- Function to load GUI settings editor ---
    def show_gui_settings(e=None):
        global CONFIG_NEEDS_REFRESH
        # 检查是否需要强制刷新
        if CONFIG_NEEDS_REFRESH:
            print("[Settings] 检测到配置变更，强制重新加载 GUI 设置")
            CONFIG_NEEDS_REFRESH = False  # 重置标记
        
        # GUI config is simpler, might not need full form generator
        # We'll load it directly from app_state and save app_state.gui_config
        print("[Settings] Loading GUI Settings Editor")
        content_area.controls.clear()

        # --- Auto-save helper ---
        def trigger_auto_save():
            # Call the existing save function silently
            save_gui_config_changes(page, app_state, silent=True)

        # --- Theme Setting --- #
        def change_theme(ev):
            selected_theme = ev.control.value.upper()
            page.theme_mode = ft.ThemeMode[selected_theme]
            app_state.gui_config["theme"] = selected_theme
            print(f"Theme changed to: {page.theme_mode}, updating app_state.gui_config")
            trigger_auto_save() # Auto-save
            page.update()  # Update theme immediately

        current_theme_val = app_state.gui_config.get("theme", str(page.theme_mode).split(".")[-1]).capitalize()
        if current_theme_val not in ["System", "Light", "Dark"]:
            current_theme_val = "System"

        theme_dropdown = ft.Dropdown(
            label="界面主题",
            value=current_theme_val,
            options=[
                ft.dropdown.Option("System"),
                ft.dropdown.Option("Light"),
                ft.dropdown.Option("Dark"),
            ],
            on_change=change_theme,
        )

        # --- Subprocess Encoding Setting (NEW) --- #
        def change_encoding(ev):
            selected_encoding = ev.control.value
            app_state.gui_config["subprocess_encoding"] = selected_encoding
            print(f"Subprocess encoding changed to: {selected_encoding}, updating app_state.gui_config")
            trigger_auto_save() # Auto-save
            # No immediate page update needed here, saving will handle persistence.

        # Get current encoding from app_state.gui_config
        current_encoding_val = app_state.gui_config.get("subprocess_encoding", "utf-8")
        if current_encoding_val not in ["utf-8", "gbk"]:
             # Fallback if value in config is invalid
            print(f"[Settings] Warning: Invalid subprocess_encoding '{current_encoding_val}' in config. Falling back to utf-8.")
            current_encoding_val = "utf-8"

        encoding_dropdown = ft.Dropdown(
            label="控制台编码",
            tooltip="用于读取 Bot/适配器 控制台输出的编码。如果中文显示乱码，尝试切换此选项。",
            value=current_encoding_val,
            options=[
                ft.dropdown.Option("utf-8", "UTF-8 (通用)"),
                ft.dropdown.Option("gbk", "GBK (旧版中文系统)"),
                # ft.dropdown.Option("system", "系统默认"), # Maybe too complex?
            ],
            on_change=change_encoding,
        )
        
        # --- Python Interpreter Path Setting --- #
        current_python_path = app_state.gui_config.get("python_path", "")
        if current_python_path:
            app_state.python_path = current_python_path
            
        python_path_textfield = ft.TextField(
            label="Python 解释器路径",
            value=current_python_path,
            expand=True,
            read_only=True,
            hint_text="选择 Python 解释器路径（留空则使用默认）",
            tooltip="选择用于运行 MaiBot 和适配器的 Python 解释器"
        )
        
        def on_python_path_result(e):
            if e.files and len(e.files) > 0:
                file_path = e.files[0].path
                python_path_textfield.value = file_path
                app_state.python_path = file_path
                app_state.gui_config["python_path"] = file_path
                print(f"[Settings] 设置 Python 路径: {file_path}")
                trigger_auto_save() # Auto-save
                page.update()

        # 设置文件选择器的回调
        app_state.file_picker.on_result = on_python_path_result
        
        # 浏览按钮
        browse_button = ft.ElevatedButton(
            "浏览...",
            icon=ft.icons.FOLDER_OPEN,
            on_click=lambda _: app_state.file_picker.pick_files(
                dialog_title="选择 Python 解释器",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["exe"],
                allow_multiple=False
            )
        )
        
        # 清除按钮
        clear_button = ft.ElevatedButton(
            "清除",
            icon=ft.icons.CLEAR,
            on_click=lambda _: (
                setattr(python_path_textfield, "value", ""),
                setattr(app_state, "python_path", ""),
                app_state.gui_config.pop("python_path", None),
                trigger_auto_save(), # Auto-save
                page.update()
            )
        )
        
        python_path_row = ft.Row(
            [python_path_textfield, browse_button, clear_button],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )

        # --- Bot Script Path Setting (NEW) --- #
        current_bot_script_path = app_state.gui_config.get("bot_script_path", "bot.py")
        # Update app_state immediately if loaded from config
        if current_bot_script_path != app_state.bot_script_path:
             app_state.bot_script_path = current_bot_script_path

        bot_script_path_textfield = ft.TextField(
            label="MaiCore 脚本路径 (bot.py)",
            value=current_bot_script_path,
            expand=True,
            hint_text="输入 bot.py 的相对或绝对路径",
            tooltip="MaiCore 主程序的启动脚本路径"
        )

        def on_bot_path_change(e):
            global CONFIG_NEEDS_REFRESH
            new_path = e.control.value.strip()
            saved = False
            if new_path:
                if app_state.bot_script_path != new_path:
                    app_state.bot_script_path = new_path
                    app_state.gui_config["bot_script_path"] = new_path
                    print(f"[Settings] MaiCore 脚本路径已暂存: {new_path}")
                    
                    # ---- 重要：更新 mmc_path ---- #
                    # 基于新的 bot_script_path 计算 mmc_path
                    try:
                        bot_script_abs_path = Path(new_path).resolve()
                        if bot_script_abs_path.is_file():
                            # 新的 bot.py 路径有效，更新 mmc_path
                            app_state.mmc_path = str(bot_script_abs_path.parent) # 改为 mmc_path
                            # 重要：同时更新 bot_base_dir
                            app_state.bot_base_dir = bot_script_abs_path.parent
                            print(f"[Settings] mmc_path 和 bot_base_dir 已更新: {app_state.mmc_path}")
                            
                            # 检查并创建 config 目录 (基于新的 mmc_path)
                            config_dir = Path(app_state.mmc_path) / "config"
                            if not config_dir.exists():
                                try:
                                    config_dir.mkdir(exist_ok=True)
                                    print(f"[Settings] 已创建 config 目录: {config_dir}")
                                except Exception as e:
                                    print(f"[Settings] 创建 config 目录失败: {e}")
                            
                            # ---- 添加：重载配置文件 ---- #
                            # 1. 重载 bot_config.toml
                            app_state.bot_config = load_config(config_type="bot", base_dir=app_state.mmc_path)
                            print(f"[Settings] 重载 bot_config: {'成功' if app_state.bot_config else '失败'}")
                            
                            # 2. 重载 lpmm_config.toml
                            app_state.lpmm_config = load_config(config_type="lpmm", base_dir=app_state.mmc_path)
                            print(f"[Settings] 重载 lpmm_config: {'成功' if app_state.lpmm_config else '失败'}")
                            
                            # 3. 检查 .env 文件
                            env_path = Path(app_state.mmc_path) / ".env"
                            env_variables = load_env_data(env_path)
                            print(f"[Settings] 检查 .env 文件: {'找到 ' + str(len(env_variables)) + ' 个变量' if env_variables else '未找到或为空'}")
                            
                            # 4. 重置数据库连接 (已有代码)
                            full_database_reset(getattr(app_state, 'db', None))
                            
                            # 5. 设置刷新标记
                            CONFIG_NEEDS_REFRESH = True
                            print("[Settings] 设置配置需要刷新标记")
                        else:
                            print(f"[Settings] 警告: 文件 {bot_script_abs_path} 不存在，但仍使用其父目录作为 mmc_path")
                            app_state.mmc_path = str(bot_script_abs_path.parent) # 改为 mmc_path
                            # 重要：同时更新 bot_base_dir
                            app_state.bot_base_dir = bot_script_abs_path.parent
                            print(f"[Settings] mmc_path 和 bot_base_dir 已更新 (文件不存在): {app_state.mmc_path}")
                            
                            # 即使文件不存在，也尝试重载配置
                            app_state.bot_config = load_config(config_type="bot", base_dir=app_state.mmc_path)
                            app_state.lpmm_config = load_config(config_type="lpmm", base_dir=app_state.mmc_path)
                            full_database_reset(getattr(app_state, 'db', None))
                            
                            # 设置刷新标记
                            CONFIG_NEEDS_REFRESH = True
                    except Exception as e:
                        print(f"[Settings] 更新 mmc_path 时出错: {e}")
                    
                    trigger_auto_save() # Auto-save
                    saved = True
            else:
                # Handle empty path? Maybe revert to default?
                if app_state.bot_script_path != "bot.py":
                    app_state.bot_script_path = "bot.py" # Revert to default if cleared
                    app_state.gui_config["bot_script_path"] = "bot.py"
                    bot_script_path_textfield.value = "bot.py" # Update textfield too
                    
                    # 重置 mmc_path 到当前工作目录 (或者一个更合适的默认值)
                    app_state.mmc_path = str(Path(".").resolve()) # 改为 mmc_path
                    # 重要：同时更新 bot_base_dir
                    app_state.bot_base_dir = Path(".").resolve()
                    print(f"[Settings] mmc_path 和 bot_base_dir 已重置: {app_state.mmc_path}")
                    
                    # ---- 添加：重载配置文件 ---- #
                    app_state.bot_config = load_config(config_type="bot", base_dir=app_state.mmc_path)
                    app_state.lpmm_config = load_config(config_type="lpmm", base_dir=app_state.mmc_path)
                    
                    full_database_reset(getattr(app_state, 'db', None)) 
                    
                    print("[Settings] MaiCore 脚本路径已清除, 恢复默认: bot.py")
                    trigger_auto_save() # Auto-save
                    saved = True
                    
                    # 设置刷新标记
                    CONFIG_NEEDS_REFRESH = True

            # Optionally provide feedback (e.g., subtle indicator or log)
            if saved:
                 print("[Settings] Auto-saved bot_script_path change.")
            # No page update needed here unless textfield value was changed programmatically

        bot_script_path_textfield.on_change = on_bot_path_change

        # (Optional) Add a file picker for bot.py
        def on_bot_script_picker_result(e: ft.FilePickerResultEvent):
            global CONFIG_NEEDS_REFRESH
            if e.files:
                chosen_path = e.files[0].path
                bot_script_path_textfield.value = chosen_path
                
                # 直接更新 mmc_path，而不依赖 on_change 事件的处理过程
                try:
                    # 计算并更新 mmc_path
                    bot_script_abs_path = Path(chosen_path).resolve()
                    if bot_script_abs_path.is_file():
                        app_state.mmc_path = str(bot_script_abs_path.parent) # 改为 mmc_path
                        # 重要：同时更新 bot_base_dir
                        app_state.bot_base_dir = bot_script_abs_path.parent
                        print(f"[Settings] 已直接更新 mmc_path 和 bot_base_dir: {app_state.mmc_path}")
                        
                        config_dir = Path(app_state.mmc_path) / "config"
                        if not config_dir.exists():
                            try:
                                config_dir.mkdir(exist_ok=True)
                                print(f"[Settings] 已创建 config 目录: {config_dir}")
                            except Exception as e:
                                print(f"[Settings] 创建 config 目录失败: {e}")
                        
                        # ---- 添加：重载配置文件 ---- #
                        # 1. 重载 bot_config.toml
                        app_state.bot_config = load_config(config_type="bot", base_dir=app_state.mmc_path)
                        print(f"[Settings] 重载 bot_config: {'成功' if app_state.bot_config else '失败'}")
                        
                        # 2. 重载 lpmm_config.toml
                        app_state.lpmm_config = load_config(config_type="lpmm", base_dir=app_state.mmc_path)
                        print(f"[Settings] 重载 lpmm_config: {'成功' if app_state.lpmm_config else '失败'}")
                        
                        # 3. 检查 .env 文件
                        env_path = Path(app_state.mmc_path) / ".env"
                        env_variables = load_env_data(env_path)
                        print(f"[Settings] 检查 .env 文件: {'找到 ' + str(len(env_variables)) + ' 个变量' if env_variables else '未找到或为空'}")
                        
                        # 4. 重置数据库连接
                        full_database_reset(getattr(app_state, 'db', None))
                        
                        # 5. 设置刷新标记
                        CONFIG_NEEDS_REFRESH = True
                        print("[Settings] 设置配置需要刷新标记")
                    else:
                        print(f"[Settings] 警告: 所选文件 {bot_script_abs_path} 不存在或无法访问")
                        app_state.mmc_path = str(bot_script_abs_path.parent) # 改为 mmc_path
                        # 重要：同时更新 bot_base_dir
                        app_state.bot_base_dir = bot_script_abs_path.parent
                        print(f"[Settings] 已直接更新 mmc_path 和 bot_base_dir (基于可能不存在的文件): {app_state.mmc_path}")
                        
                        # 即使文件不存在，也尝试重载配置
                        app_state.bot_config = load_config(config_type="bot", base_dir=app_state.mmc_path)
                        app_state.lpmm_config = load_config(config_type="lpmm", base_dir=app_state.mmc_path)
                        
                        full_database_reset(getattr(app_state, 'db', None))
                        
                        # 设置刷新标记
                        CONFIG_NEEDS_REFRESH = True
                except Exception as e:
                    print(f"[Settings] 直接更新 mmc_path 时出错: {e}")
                
                # 触发现有的更改处理逻辑
                # Trigger the on_change handler to update state and auto-save
                on_bot_path_change(ft.ControlEvent(target=bot_script_path_textfield.uid, name="change", data=chosen_path, control=bot_script_path_textfield, page=page))
                page.update()

        bot_script_picker = ft.FilePicker(on_result=on_bot_script_picker_result)
        page.overlay.append(bot_script_picker) # Add picker to overlay

        browse_bot_script_button = ft.ElevatedButton(
            "浏览...",
            icon=ft.icons.FOLDER_OPEN,
            on_click=lambda _: bot_script_picker.pick_files(
                dialog_title="选择 MaiCore 脚本 (bot.py)",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["py"],
                allow_multiple=False
            )
        )

        bot_script_path_row = ft.Row(
            [bot_script_path_textfield, browse_bot_script_button],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )

        # --- 添加下载卡片 --- #
        download_card = ft.Card(
            content=ft.Container(
                ft.Column(
                    [
                        ft.Text("安装MMC与Python环境", weight=ft.FontWeight.BOLD, size=16),
                        ft.Row(
                            [
                                ft.ElevatedButton(
                                    "下载MMC", 
                                    icon=ft.icons.DOWNLOAD,
                                    on_click=download_mmc,
                                    tooltip="下载MaiBot-Core (MMC)仓库"
                                ),
                                ft.ElevatedButton(
                                    "安装Python", 
                                    icon=ft.icons.CODE,
                                    on_click=install_python,
                                    tooltip="前往Python官方网站下载安装Python"
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                            spacing=10,
                        ),
                    ],
                    spacing=10
                ),
                padding=20,
            ),
            margin=ft.margin.only(bottom=10)
        )

        content_area.controls.extend(
            [
                download_card,  # 添加下载卡片
                ft.Card(
                    content=ft.Container(
                        ft.Column(
                            [
                                ft.Text("界面与显示", weight=ft.FontWeight.BOLD, size=16),
                                theme_dropdown,
                                encoding_dropdown,
                            ]
                        ),
                        padding=10,
                    )
                ),
                ft.Card(
                    content=ft.Container(
                        ft.Column(
                            [
                                ft.Text("路径设置", weight=ft.FontWeight.BOLD, size=16),
                                ft.Text("Python 解释器:", weight=ft.FontWeight.W_500),
                                python_path_row,
                                ft.Text("MaiCore 主程序:", weight=ft.FontWeight.W_500),
                                bot_script_path_row,
                            ]
                        ),
                        padding=10,
                    )
                ),
            ]
        )
        if page:
            page.update()

    # --- Initial View Setup ---
    # Load the GUI settings editor by default
    show_gui_settings()

    return ft.View(
        "/settings",
        [
            ft.AppBar(title=ft.Text("设置"), bgcolor=ft.colors.SURFACE_VARIANT),
            ft.Row(
                [
                    ft.ElevatedButton("麦麦Core 配置", icon=ft.icons.SETTINGS_SUGGEST, on_click=show_bot_config_editor),
                    ft.ElevatedButton("LPMM 配置", icon=ft.icons.MEMORY, on_click=show_lpmm_editor),
                    ft.ElevatedButton("启动器设置", icon=ft.icons.BRUSH, on_click=show_gui_settings),
                    ft.ElevatedButton(".env 配置", icon=ft.icons.EDIT, on_click=show_env_editor),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                wrap=True,  # Allow buttons to wrap on smaller widths
            ),
            ft.Divider(),
            content_area,  # This holds the currently selected editor
        ],
        scroll=ft.ScrollMode.ADAPTIVE,
    )


# Note: Assumes save_config function exists and can handle saving
# the bot_config dictionary back to its TOML file. You might need to
# adjust the save_bot_config_changes function based on how saving is implemented.
# Also assumes load_bot_config loads the data correctly for the TOML editor.


def create_settings_view_old(page: ft.Page, app_state: AppState) -> ft.View:
    """创建设置页面视图。"""

    # --- GUI Settings ---
    def change_theme(e):
        selected_theme = e.control.value.upper()
        page.theme_mode = ft.ThemeMode[selected_theme]
        # Persist theme choice? Maybe in gui_config?
        app_state.gui_config["theme"] = selected_theme  # Example persistence
        # Need a way to save gui_config too (similar to bot_config?)
        print(f"Theme changed to: {page.theme_mode}")
        page.update()

    theme_dropdown = ft.Dropdown(
        label="界面主题",
        value=str(page.theme_mode).split(".")[-1].capitalize()
        if page.theme_mode
        else "System",  # Handle None theme_mode
        options=[
            ft.dropdown.Option("System"),
            ft.dropdown.Option("Light"),
            ft.dropdown.Option("Dark"),
        ],
        on_change=change_theme,
        expand=True,
    )

    gui_settings_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.ListTile(title=ft.Text("GUI 设置")),
                    ft.Row([theme_dropdown], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    # Add more GUI settings here
                ]
            ),
            padding=10,
        )
    )

    # --- Bot Settings (Placeholder) ---
    # TODO: Load bot_config.toml and dynamically generate controls
    config_path = get_bot_config_path(app_state)
    bot_config_content_area = ft.Column(expand=True, scroll=ft.ScrollMode.ADAPTIVE)
    bot_settings_card = ft.Card(
        content=ft.Container(
            content=ft.Column(
                [
                    ft.ListTile(title=ft.Text("Bot 配置 (bot_config.toml)")),
                    ft.Text(f"配置文件路径: {config_path}", italic=True, size=10),
                    ft.Divider(),
                    # Placeholder - Controls will be added dynamically
                    bot_config_content_area,
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "重新加载", icon=ft.icons.REFRESH, on_click=lambda _: print("Reload TBD")
                            ),  # Placeholder action
                            ft.ElevatedButton(
                                "保存 Bot 配置", icon=ft.icons.SAVE, on_click=lambda _: print("Save TBD")
                            ),  # Placeholder action
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ]
            ),
            padding=10,
        )
    )

    # --- Load and Display Bot Config ---
    # This needs error handling and dynamic UI generation
    try:
        # 使用新的加载方法
        loaded_bot_config = load_bot_config(app_state)

        if loaded_bot_config:
            # 使用新的表单生成器创建动态表单
            create_toml_form(page, loaded_bot_config, bot_config_content_area, app_state)

            # Update the save button's action
            save_button = bot_settings_card.content.content.controls[-1].controls[1]  # Find the save button
            save_button.on_click = lambda _: save_bot_config(
                page, app_state, loaded_bot_config
            )  # Pass the loaded config dict

            # Add reload logic here
            reload_button = bot_settings_card.content.content.controls[-1].controls[0]  # Find the reload button

            def reload_action(_):
                bot_config_content_area.controls.clear()
                try:
                    reloaded_config = load_bot_config(app_state)
                    if reloaded_config:
                        # 重新创建表单
                        create_toml_form(page, reloaded_config, bot_config_content_area, app_state)
                        # Update save button reference
                        save_button.on_click = lambda _: save_bot_config(page, app_state, reloaded_config)
                        show_snackbar(page, "Bot 配置已重新加载。")
                        # 确保UI完全更新
                        bot_config_content_area.update()
                        bot_settings_card.update()
                    else:
                        bot_config_content_area.controls.append(
                            ft.Text("重新加载失败: 无法加载配置文件", color=ft.colors.ERROR)
                        )
                        bot_config_content_area.update()
                except Exception as reload_e:
                    bot_config_content_area.controls.append(ft.Text(f"重新加载失败: {reload_e}", color=ft.colors.ERROR))
                    bot_config_content_area.update()
                page.update()

            reload_button.on_click = reload_action
        else:
            bot_config_content_area.controls.append(
                ft.Text(f"错误: 无法加载配置文件 {config_path}", color=ft.colors.ERROR)
            )
    except Exception as e:
        bot_config_content_area.controls.append(ft.Text(f"加载配置文件出错: {e}", color=ft.colors.ERROR))

    return ft.View(
        "/settings",
        [
            ft.AppBar(title=ft.Text("设置"), bgcolor=ft.colors.SURFACE_VARIANT),
            gui_settings_card,
            bot_settings_card,  # Add the bot settings card
            # Add more settings sections/cards as needed
        ],
        scroll=ft.ScrollMode.ADAPTIVE,  # Allow scrolling for the whole view
        padding=10,
    )

