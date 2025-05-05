import flet as ft
import tomlkit

from .state import AppState
from .utils import show_snackbar  # Assuming show_snackbar is in utils
from .toml_form_generator import create_toml_form, load_bot_config, get_bot_config_path
from .config_manager import load_config, save_config
from .ui_env_editor import create_env_editor_page_content


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


def save_bot_config_changes(page: ft.Page, config_to_save: dict, silent: bool = False):
    """Handles saving changes for bot_config.toml"""
    if not silent:
        print("[Settings] Saving Bot Config (TOML) changes...")
    # Assuming save_config needs path, let's build it or adapt save_config
    # For now, let's assume save_config can handle type='bot'
    # config_path = get_bot_config_path(app_state) # Need app_state if using this
    success = save_config(config_to_save, config_type="bot")
    if not silent:
        if success:
            message = "Bot 配置已保存！"
        else:
            message = "保存 Bot 配置失败。"
        show_snackbar(page, message, error=(not success))
    elif not success:
        print("[Settings] Error during silent save of Bot Config.")


def save_lpmm_config_changes(page: ft.Page, config_to_save: dict, silent: bool = False):
    """Handles saving changes for lpmm_config.toml"""
    if not silent:
        print("[Settings] Saving LPMM Config (TOML) changes...")
    success = save_config(config_to_save, config_type="lpmm")  # Use type 'lpmm'
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
    success = save_config(app_state.gui_config, config_type="gui")
    if not silent: # Only show snackbar if not silent
        if success:
            message = "GUI 配置已保存！"
        else:
            message = "保存 GUI 配置失败。"
        show_snackbar(page, message, error=(not success))
    elif not success: # Still log error even if silent
        print("[Settings] Error during silent save of GUI Config.")


def create_settings_view(page: ft.Page, app_state: AppState) -> ft.View:
    """Creates the settings view with sections for different config files."""

    # --- State for switching between editors ---
    content_area = ft.Column([], expand=True, scroll=ft.ScrollMode.ADAPTIVE)
    current_config_data = {}  # Store loaded data for saving

    # --- Function to load Bot config editor (Original TOML editor) ---
    def show_bot_config_editor(e=None):
        nonlocal current_config_data
        print("[Settings] Loading Bot Config Editor")
        try:
            current_bot_config = load_bot_config(app_state)
            if not current_bot_config:
                raise ValueError("Bot config could not be loaded.")
            current_config_data = current_bot_config # Keep reference if needed elsewhere
            content_area.controls.clear()

            # Define the save callback for the bot config
            def bot_save_callback(data_to_save):
                return save_bot_config_changes(page, data_to_save, silent=True)

            # Pass the callback to the form generator
            form_generator = create_toml_form(
                page,
                current_bot_config, # Pass the data directly
                content_area,
                template_filename="bot_config_template.toml",
                save_callback=bot_save_callback,
                debounce_interval=1.5 # Optional: slightly longer debounce
            )
            # No explicit save button needed anymore
            # save_button = ft.ElevatedButton(...)
            # content_area.controls.append(ft.Divider())
            # content_area.controls.append(save_button)
        except Exception as ex:
            content_area.controls.clear()
            content_area.controls.append(ft.Text(f"加载 Bot 配置时出错: {ex}", color=ft.colors.ERROR))
        if page:
            page.update()

    # --- Function to load LPMM config editor ---
    def show_lpmm_editor(e=None):
        nonlocal current_config_data
        print("[Settings] Loading LPMM Config Editor")
        try:
            lpmm_config = load_config(config_type="lpmm")
            if not lpmm_config:
                raise ValueError("LPMM config could not be loaded.")
            current_config_data = lpmm_config # Keep reference
            content_area.controls.clear()

            # Define the save callback for LPMM config
            def lpmm_save_callback(data_to_save):
                return save_lpmm_config_changes(page, data_to_save, silent=True)

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

    # --- Function to load GUI settings editor ---
    def show_gui_settings(e=None):
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
            new_path = e.control.value.strip()
            saved = False
            if new_path:
                if app_state.bot_script_path != new_path:
                    app_state.bot_script_path = new_path
                    app_state.gui_config["bot_script_path"] = new_path
                    print(f"[Settings] MaiCore 脚本路径已暂存: {new_path}")
                    trigger_auto_save() # Auto-save
                    saved = True
            else:
                # Handle empty path? Maybe revert to default?
                if app_state.bot_script_path != "bot.py":
                    app_state.bot_script_path = "bot.py" # Revert to default if cleared
                    app_state.gui_config["bot_script_path"] = "bot.py"
                    bot_script_path_textfield.value = "bot.py" # Update textfield too
                    print("[Settings] MaiCore 脚本路径已清除, 恢复默认: bot.py")
                    trigger_auto_save() # Auto-save
                    saved = True
            # Optionally provide feedback (e.g., subtle indicator or log)
            if saved:
                 print("[Settings] Auto-saved bot_script_path change.")
            # No page update needed here unless textfield value was changed programmatically

        bot_script_path_textfield.on_change = on_bot_path_change

        # (Optional) Add a file picker for bot.py
        def on_bot_script_picker_result(e: ft.FilePickerResultEvent):
            if e.files:
                chosen_path = e.files[0].path
                bot_script_path_textfield.value = chosen_path
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

        # --- Save Button (REMOVED) --- #
        # save_button = ft.ElevatedButton(
        #     "保存通用设置", icon=ft.icons.SAVE, on_click=lambda _: save_gui_config_changes(page, app_state)
        # )

        content_area.controls.extend(
            [
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
                # ft.Divider(), # Divider no longer needed before save button
                # save_button, # Removed save button
            ]
        )
        if page:
            page.update()

    # --- Function to load .env editor ---
    def show_env_editor(e=None):
        # No config data to manage here, it handles its own save
        print("[Settings] Loading .env Editor")
        content_area.controls.clear()
        env_editor_content = create_env_editor_page_content(page, app_state)
        content_area.controls.append(env_editor_content)
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
