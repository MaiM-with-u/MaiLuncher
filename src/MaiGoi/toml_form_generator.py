import flet as ft
import tomlkit
from typing import Dict, Any, List, Optional, Union, Callable
from pathlib import Path
import time # Import time for debouncing
import threading

# --- Define callback type for saving ---
# Takes config data and returns success boolean
SaveCallback = Callable[[Dict[str, Any]], bool]

def load_template_with_comments(template_filename: str = "bot_config_template.toml"):
    """
    加载指定的模板文件，保留所有注释。

    Args:
        template_filename: 要加载的模板文件名 (相对于 template/ 目录)。

    Returns:
        包含注释的TOML文档对象，如果失败则返回空文档。
    """
    try:
        # 首先尝试从相对路径加载 (相对于项目根目录)
        # 假设此脚本位于 src/MaiGoi/
        base_path = Path(__file__).parent.parent.parent
        template_path = base_path / "template" / template_filename

        if template_path.exists():
            print(f"找到模板文件: {template_path}")
            with open(template_path, "r", encoding="utf-8") as f:
                return tomlkit.parse(f.read())
        else:
            print(f"警告: 模板文件不存在: {template_path}")
            return tomlkit.document()
    except Exception as e:
        print(f"加载模板文件 '{template_filename}' 出错: {e}")
        return tomlkit.document()


def get_comment_for_key(template_doc, key_path: str) -> str:
    """
    获取指定键路径的注释 (修正版)

    Args:
        template_doc: 包含注释的TOML文档
        key_path: 点分隔的键路径，例如 "bot.qq"

    Returns:
        该键对应的注释字符串，如果没有则返回空字符串
    """
    if not template_doc:
        return ""

    try:
        parts = key_path.split(".")
        current_item = template_doc

        # 逐级导航到目标项或其父表
        for i, part in enumerate(parts):
            if part not in current_item:
                print(f"警告: 路径部分 '{part}' 在 {'.'.join(parts[:i])} 中未找到")
                return ""  # 路径不存在

            # 如果是最后一个部分，我们找到了目标项
            if i == len(parts) - 1:
                target_item = current_item[part]

                # --- 尝试从 trivia 获取注释 ---
                if hasattr(target_item, "trivia") and hasattr(target_item.trivia, "comment"):
                    comment_lines = target_item.trivia.comment.split("\n")
                    # 去除每行的 '#' 和首尾空格
                    cleaned_comment = "\n".join([line.strip().lstrip("#").strip() for line in comment_lines])
                    if cleaned_comment:
                        return cleaned_comment

                # --- 如果是顶级表，也检查容器自身的 trivia ---
                # (tomlkit 对于顶级表的注释存储方式可能略有不同)
                if isinstance(target_item, (tomlkit.items.Table, tomlkit.container.Container)) and len(parts) == 1:
                    if hasattr(target_item, "trivia") and hasattr(target_item.trivia, "comment"):
                        comment_lines = target_item.trivia.comment.split("\n")
                        cleaned_comment = "\n".join([line.strip().lstrip("#").strip() for line in comment_lines])
                        if cleaned_comment:
                            return cleaned_comment

                # 如果 trivia 中没有，尝试一些旧版或不常用的属性 (风险较高)
                # if hasattr(target_item, '_comment'): # 不推荐
                #    return str(target_item._comment).strip(" #")

                # 如果以上都找不到，返回空
                return ""

            # 继续导航到下一级
            current_item = current_item[part]
            # 如果中间路径不是表/字典，则无法继续
            if not isinstance(current_item, (dict, tomlkit.items.Table, tomlkit.container.Container)):
                print(f"警告: 路径部分 '{part}' 指向的不是表结构，无法继续导航")
                return ""

        return ""  # 理论上不应执行到这里，除非 key_path 为空

    except Exception as e:
        # 打印更详细的错误信息，包括路径和异常类型
        print(f"获取注释时发生意外错误 (路径: {key_path}): {type(e).__name__} - {e}")
        # print(traceback.format_exc()) # 可选：打印完整堆栈跟踪
        return ""


class TomlFormGenerator:
    """用于将TOML配置生成Flet表单控件并支持自动保存的类。"""

    def __init__(
        self,
        page: ft.Page,
        config_data: Dict[str, Any],
        parent_container: ft.Column,
        template_filename: str = "bot_config_template.toml",
        save_callback: Optional[SaveCallback] = None, # Callback for saving
        debounce_interval: float = 1.0, # Debounce time in seconds
    ):
        """
        初始化表单生成器。

        Args:
            page: Flet Page 对象
            config_data: TOML配置数据（嵌套字典）
            parent_container: 要添加控件的父容器
            template_filename: 要使用的模板文件名
            save_callback: 保存配置的回调函数
            debounce_interval: 自动保存的防抖间隔（秒）
        """
        self.page = page
        self.config_data = config_data
        self.parent_container = parent_container
        self.controls_map = {}
        self.expanded_sections = set()
        self.save_callback = save_callback # Store the save callback
        self.debounce_interval = debounce_interval
        self.last_change_time = 0
        self.save_timer: Optional[threading.Timer] = None # For debouncing

        # 加载指定的模板文档
        self.template_doc = load_template_with_comments(template_filename)

        if not self.template_doc.value:
            print(f"警告：加载的模板 '{template_filename}' 为空，注释功能将不可用。")

    def build_form(self):
        """构建整个表单。"""
        self.parent_container.controls.clear()
        self.controls_map.clear()  # 清空控件映射
        # 使用 self.config_data 构建表单
        self._process_toml_section(self.config_data, self.parent_container)

    def _get_comment(self, key_path: str) -> str:
        """获取指定键路径的注释，并确保结果是字符串"""
        try:
            comment = get_comment_for_key(self.template_doc, key_path)
            # 确保返回值是字符串
            if comment and isinstance(comment, str):
                return comment
        except Exception as e:
            print(f"获取注释出错: {key_path}, {e}")
        return ""  # 如果出现任何问题，返回空字符串

    def _process_toml_section(
        self,
        section_data: Dict[str, Any],
        container: Union[ft.Column, ft.Container],
        section_path: str = "",
        indent: int = 0,
    ):
        """
        递归处理TOML配置的一个部分。

        Args:
            section_data: 要处理的配置部分
            container: 放置控件的容器（可以是Column或Container）
            section_path: 当前部分的路径（用于跟踪嵌套层级）
            indent: 当前缩进级别
        """
        # 确保container是有controls属性的对象
        if isinstance(container, ft.Container):
            if container.content and hasattr(container.content, "controls"):
                container = container.content
            else:
                # 如果Container没有有效的content，创建一个Column
                container.content = ft.Column([])
                container = container.content

        if not hasattr(container, "controls"):
            raise ValueError(f"传递给_process_toml_section的容器必须有controls属性，got: {type(container)}")

        # 先处理所有子部分（嵌套表）
        subsections = {}
        simple_items = {}

        # 分离子部分和简单值
        for key, value in section_data.items():
            if isinstance(value, (dict, tomlkit.items.Table)):
                subsections[key] = value
            else:
                simple_items[key] = value

        # 处理简单值
        for key, value in simple_items.items():
            full_path = f"{section_path}.{key}" if section_path else key
            control = self._create_control_for_value(key, value, full_path)
            if control:
                if indent > 0:  # 添加缩进
                    row = ft.Row(
                        [
                            ft.Container(width=indent * 20),  # 每级缩进20像素
                            control,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    )
                    container.controls.append(row)
                else:
                    container.controls.append(control)

        # 处理子部分
        for key, value in subsections.items():
            full_path = f"{section_path}.{key}" if section_path else key

            # 创建一个可展开/折叠的部分
            is_expanded = full_path in self.expanded_sections

            # 获取此部分的注释（安全获取）
            section_comment = self._get_comment(full_path)

            # 创建子部分的标题行
            section_title_elems = [
                ft.Container(width=indent * 20) if indent > 0 else ft.Container(width=0),
                ft.IconButton(
                    icon=ft.icons.ARROW_DROP_DOWN if is_expanded else ft.icons.ARROW_RIGHT,
                    on_click=lambda e, path=full_path: self._toggle_section(e, path),
                ),
                ft.Text(key, weight=ft.FontWeight.BOLD, size=16),
            ]

            # 如果有注释，添加一个Info图标并设置tooltip
            if section_comment and len(section_comment) > 0:
                try:
                    section_title_elems.append(
                        ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=section_comment, icon_size=16)
                    )
                except Exception as e:
                    print(f"创建信息图标时出错: {full_path}, {e}")

            section_title = ft.Row(
                section_title_elems,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

            container.controls.append(section_title)

            # 创建子部分的容器
            subsection_column = ft.Column([])
            subsection_container = ft.Container(content=subsection_column, visible=is_expanded)
            container.controls.append(subsection_container)

            # 递归处理子部分
            self._process_toml_section(
                value, subsection_column, full_path, indent + 1
            )

    def _toggle_section(self, e, section_path):
        """切换部分展开/折叠状态并强制刷新页面。"""
        container = e.control.parent.parent.controls[e.control.parent.parent.controls.index(e.control.parent) + 1]
        if section_path in self.expanded_sections:
            self.expanded_sections.remove(section_path)
            e.control.icon = ft.icons.ARROW_RIGHT
            container.visible = False
        else:
            self.expanded_sections.add(section_path)
            e.control.icon = ft.icons.ARROW_DROP_DOWN
            container.visible = True

        # 强制页面更新以反映可见性变化
        self.page.update()

    def _trigger_debounced_save(self):
        """Triggers the save callback after a debounce interval."""
        if not self.save_callback:
            return

        # Cancel any existing timer
        if self.save_timer:
            self.save_timer.cancel()

        # Define the function to be called by the timer
        def save_action():
            print(f"[Debounce] Triggering save callback at {time.time():.2f}")
            self.save_callback(self.config_data)
            self.save_timer = None # Clear timer after execution

        # Schedule the save action
        self.save_timer = threading.Timer(self.debounce_interval, save_action)
        self.save_timer.start()
        print(f"[Debounce] Save scheduled in {self.debounce_interval}s at {time.time():.2f}")

    def _update_config_value(self, path: str, new_value: Any):
        """更新配置字典中的值。"""
        try:
            keys = path.split('.')
            data = self.config_data
            for i, key in enumerate(keys):
                if i == len(keys) - 1:
                    # Check if value actually changed to avoid unnecessary saves
                    if key in data and data[key] == new_value:
                        return # No change, do nothing
                    data[key] = new_value
                    print(f"[Config Update] Path: {path}, New Value: {new_value}")
                    # Trigger debounced save after updating the value
                    self._trigger_debounced_save()
                else:
                    if key not in data or not isinstance(data[key], dict):
                        # This case might indicate an issue if the structure changes unexpectedly
                        print(f"Warning: Path {path} structure issue at key {key}. Creating dict.")
                        data[key] = {}
                    data = data[key]
        except Exception as e:
            print(f"Error updating config value for path {path}: {e}")
            import traceback
            traceback.print_exc()

    def _create_control_for_value(self, key: str, value: Any, full_path: str) -> Optional[ft.Control]:
        """根据值的类型创建合适的Flet控件。"""
        comment = self._get_comment(full_path)

        control_type = type(value)
        if isinstance(value, bool):
            return self._create_boolean_control(key, value, full_path, comment)
        elif isinstance(value, (int, float)):
            return self._create_number_control(key, value, full_path, comment)
        elif isinstance(value, str):
            return self._create_string_control(key, value, full_path, comment)
        elif isinstance(value, (list, tomlkit.items.Array)):
            # Ensure it's a list for processing
            return self._create_list_control(key, list(value), full_path, comment)
        elif isinstance(value, set): # Handle sets if needed
             return self._create_set_control(key, value, full_path, comment)
        else:
            print(f"不支持的配置类型: {control_type} for key '{key}'")
            return ft.Text(f"{key}: Unsupported type ({control_type})", color=ft.colors.RED)

    def _create_boolean_control(self, key: str, value: bool, path: str, comment: str = "") -> ft.Control:
        control = ft.Checkbox(label=key, value=value, tooltip=comment)
        control.on_change = lambda e: self._update_config_value(path, e.control.value)
        return control

    def _create_number_control(self, key: str, value: Union[int, float], path: str, comment: str = "") -> ft.Control:
        control = ft.TextField(
            label=key,
            value=str(value),
            tooltip=comment,
            keyboard_type=ft.KeyboardType.NUMBER,
            suffix_text="(数字)"
        )
        # Add on_change handler
        control.on_change = lambda e: self._handle_number_change(path, e.control.value)
        return control

    def _handle_number_change(self, path: str, text_value: str):
        """Handle changes for number TextFields, converting and validating."""
        try:
            # Try converting to float first, then int if possible
            num_value = float(text_value)
            if num_value.is_integer():
                num_value = int(num_value)
            self._update_config_value(path, num_value)
        except ValueError:
            # Handle invalid input (optional: show error, revert?)
            print(f"Invalid number input for {path}: {text_value}")
            # Maybe find the control and set error text?
            # control = self.controls_map.get(path)
            # if control: control.error_text = "请输入有效数字"

    def _create_string_control(self, key: str, value: str, path: str, comment: str = "") -> ft.Control:
        is_multiline = "\n" in value or len(value) > 60 # Simple heuristic for multiline
        control = ft.TextField(
            label=key,
            value=value,
            tooltip=comment,
            multiline=is_multiline,
            min_lines=3 if is_multiline else 1,
            max_lines=10 if is_multiline else 1,
            expand=not is_multiline, # Expand single line text fields
            # keyboard_type=ft.KeyboardType.TEXT, # Default
        )
        control.on_change = lambda e: self._update_config_value(path, e.control.value)
        return control

    def _create_list_control(self, key: str, value: List[Any], path: str, comment: str = "") -> ft.Control:
        """为列表类型创建控件 (修改以支持自动保存)"""
        items_column = ft.Column([]) # Column to hold list item controls
        self.controls_map[path] = items_column # Store the column itself for adding items

        # Keep track of current items and their controls within this instance
        list_item_controls = {} # Maps item control UID to its value/row

        def update_list_value():
            """Reads current item controls and updates the config data."""
            new_list = []
            # Iterate through controls in the items_column
            for row_control in items_column.controls:
                if isinstance(row_control, ft.Row) and len(row_control.controls) > 1:
                    item_control = row_control.controls[0] # Assuming TextField is first
                    if isinstance(item_control, ft.TextField):
                        # Attempt type conversion based on original list type if needed
                        # For simplicity, assuming string list for now
                        new_list.append(item_control.value)
                    elif isinstance(item_control, ft.Checkbox): # Example for list of booleans
                        new_list.append(item_control.value)
                    # Add more types as needed
            print(f"Updating list {path} to: {new_list}")
            self._update_config_value(path, new_list) # Trigger update and auto-save

        def on_item_change(e):
            """Callback when an item's TextField/Checkbox changes."""
            # Find the control that triggered the event
            trigger_control = e.control
            # Find its parent row
            parent_row = None
            for row in items_column.controls:
                if isinstance(row, ft.Row) and trigger_control in row.controls:
                    parent_row = row
                    break

            if parent_row:
                # Update the internal tracking (optional, update_list_value reads directly)
                # list_item_controls[parent_row.uid]['value'] = trigger_control.value
                # print(f"Item changed: {trigger_control.value}")
                update_list_value() # Update the whole list in config data
            else:
                print("Warning: Could not find parent row for list item change.")

        def delete_item(e):
            """Deletes an item from the list UI and triggers update."""
            row_to_delete = e.control.data # The Row control stored in button's data
            if row_to_delete in items_column.controls:
                items_column.controls.remove(row_to_delete)
                # Remove from tracking dict
                if row_to_delete.uid in list_item_controls:
                    del list_item_controls[row_to_delete.uid]
                print(f"Deleted item row: {row_to_delete.uid}")
                update_list_value() # Update the list in config data
                self.page.update() # Update UI immediately
            else:
                print("Warning: Row to delete not found in items column.")

        def add_item(e=None, item_value="", is_initial=False):
            """Adds a new item control to the list UI."""
            # Determine control type based on list content (simple: assume string)
            # TODO: Add logic to infer type or handle mixed lists if needed
            item_control = ft.TextField(value=str(item_value))
            item_control.on_change = on_item_change # Attach change handler

            delete_button = ft.IconButton(
                ft.icons.DELETE_OUTLINE,
                tooltip="删除此项",
                icon_color=ft.colors.RED_ACCENT_200,
                on_click=delete_item
            )
            new_row = ft.Row([item_control, delete_button], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            delete_button.data = new_row # Store row reference in button

            items_column.controls.append(new_row)
            list_item_controls[new_row.uid] = {'row': new_row, 'control': item_control}

            if not is_initial:
                update_list_value() # Update config data when item added manually
                self.page.update()

        # Populate initial items
        for item in value:
            add_item(item_value=item, is_initial=True)

        # Add button to add new items
        add_button = ft.ElevatedButton("添加新项", icon=ft.icons.ADD, on_click=add_item)

        # Main container for the list control
        list_container = ft.Column(
            [
                ft.Row([ft.Text(key, weight=ft.FontWeight.BOLD), ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=comment, icon_size=14) if comment else ft.Container()], vertical_alignment=ft.CrossAxisAlignment.CENTER), # Title row
                ft.Divider(),
                ft.Container(items_column, border=ft.border.all(1, ft.colors.OUTLINE), padding=5), # Items area
                add_button, # Add button
            ],
            spacing=5,
        )
        return list_container

    def _create_set_control(self, key: str, value: set, path: str, comment: str = "") -> ft.Control:
        """为集合类型创建控件 (修改以支持自动保存)"""
        items_column = ft.Column([], spacing=2, scroll=ft.ScrollMode.ADAPTIVE)
        self.controls_map[path] = items_column # Store the column itself

        # Keep track of current items and their controls
        set_item_controls = {} # Maps item TEXT (value) to its Row control

        def update_set_value():
            """Reads current item controls and updates the config data."""
            new_set = set()
            # Iterate through tracked controls (using values from the dict)
            for item_text in list(set_item_controls.keys()): # Iterate over a copy of keys
                # Assume items are strings for simplicity in sets
                new_set.add(item_text)

            print(f"Updating set {path} to: {new_set}")
            # Convert set back to list for saving if TOML library requires it
            # (tomlkit might handle sets directly, but list is safer)
            self._update_config_value(path, list(new_set)) # Trigger update and auto-save

        def delete_item(e):
            """Deletes an item from the set UI and triggers update."""
            row_to_delete = e.control.data # The Row control stored in button's data
            item_text_to_delete = None
            # Find the text associated with this row
            for text, row in set_item_controls.items():
                if row == row_to_delete:
                    item_text_to_delete = text
                    break

            if item_text_to_delete is not None and row_to_delete in items_column.controls:
                items_column.controls.remove(row_to_delete)
                del set_item_controls[item_text_to_delete]
                print(f"Deleted set item: {item_text_to_delete}")
                update_set_value() # Update the set in config data
                self.page.update() # Update UI immediately
            else:
                print(f"Warning: Row/Item to delete not found for set {path}.")

        def add_item_from_field(e=None, item_text=""):
            """Adds a new item from the input field to the set UI."""
            if not item_text:
                item_text = add_item_field.value.strip()

            if not item_text:
                return # Ignore empty input

            # Check for duplicates
            if item_text in set_item_controls:
                 if self.page: # Show feedback if page context is available
                     self.page.show_snack_bar(ft.SnackBar(ft.Text(f"项目 '{item_text}' 已存在于集合中"), open=True))
                 add_item_field.value = "" # Clear field even if duplicate
                 add_item_field.update()
                 return

            # Create UI elements for the new item
            item_label = ft.Text(item_text, expand=True)
            delete_button = ft.IconButton(
                ft.icons.DELETE_OUTLINE,
                tooltip="删除此项",
                icon_color=ft.colors.RED_ACCENT_200,
                on_click=delete_item
            )
            new_row = ft.Row([item_label, delete_button], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            delete_button.data = new_row # Store row reference

            # Add to UI and tracking dict
            items_column.controls.append(new_row)
            set_item_controls[item_text] = new_row

            # Clear input field and update UI
            add_item_field.value = ""
            update_set_value() # Update config data
            self.page.update()

        # Populate initial items
        for item in sorted(list(value)): # Sort for consistent display order
            item_str = str(item) # Ensure string representation
            # Create UI elements (similar to add_item_from_field but without adding to config yet)
            item_label = ft.Text(item_str, expand=True)
            delete_button = ft.IconButton(
                ft.icons.DELETE_OUTLINE,
                tooltip="删除此项",
                icon_color=ft.colors.RED_ACCENT_200,
                on_click=delete_item
            )
            row = ft.Row([item_label, delete_button], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            delete_button.data = row # Store row reference
            items_column.controls.append(row)
            set_item_controls[item_str] = row # Add to tracking

        # Input field for adding new items
        add_item_field = ft.TextField(
            label="添加新项到集合",
            hint_text="输入值后按 Enter 或点击按钮",
            expand=True,
            on_submit=lambda e: add_item_from_field(e, e.control.value) # Use on_submit for Enter key
        )

        add_button = ft.IconButton(
            icon=ft.icons.ADD_CIRCLE_OUTLINE,
            tooltip="添加项目到集合",
            on_click=lambda e: add_item_from_field(e, add_item_field.value) # Click handler
        )

        # Main container for the set control
        set_container = ft.Column(
            [
                ft.Row([ft.Text(key, weight=ft.FontWeight.BOLD), ft.IconButton(icon=ft.icons.INFO_OUTLINE, tooltip=comment, icon_size=14) if comment else ft.Container()], vertical_alignment=ft.CrossAxisAlignment.CENTER), # Title row
                ft.Divider(),
                ft.Container(items_column, border=ft.border.all(1, ft.colors.OUTLINE), padding=5, height=150), # Items area with fixed height
                ft.Row([add_item_field, add_button], alignment=ft.MainAxisAlignment.START) # Add row
            ],
            spacing=5,
        )
        return set_container


def load_bot_config_template(app_state) -> Dict[str, Any]:
    # Helper function to load bot_config template
    # Assuming you have this logic already or can adapt it
    template_doc = load_template_with_comments("bot_config_template.toml")
    # Convert tomlkit doc to plain dict if needed
    return dict(template_doc)

def get_bot_config_path(app_state) -> Path:
    # Helper to get the path, assuming config_manager can provide it
    from .config_manager import get_config_path
    
    # 重要：使用 app_state.bot_base_dir 作为 base_dir 参数
    if not hasattr(app_state, 'bot_base_dir') or not app_state.bot_base_dir:
        print("[toml_form_generator] Error: app_state.bot_base_dir 未设置，无法确定 bot_config.toml 路径")
        raise ValueError("app_state.bot_base_dir is not set, cannot determine bot_config.toml path")
    
    path = get_config_path("bot", base_dir=app_state.bot_base_dir)
    if not path:
        raise FileNotFoundError(f"Could not determine path for bot_config.toml in {app_state.bot_base_dir}/config/")
    
    print(f"[toml_form_generator] 确定 bot_config.toml 路径: {path}")
    return path

def load_bot_config(app_state) -> Dict[str, Any]:
    """加载 Bot 配置文件 (bot_config.toml)"""
    from .config_manager import load_config

    try:
        # 直接使用 app_state.bot_base_dir 作为 base_dir 参数
        if not hasattr(app_state, 'bot_base_dir') or not app_state.bot_base_dir:
            print("[toml_form_generator] Error: app_state.bot_base_dir 未设置，无法加载 bot_config.toml")
            raise ValueError("app_state.bot_base_dir is not set, cannot load bot_config.toml")
            
        print(f"[toml_form_generator] 尝试从 {app_state.bot_base_dir}/config/ 加载 Bot 配置")
        
        # 正确使用 app_state.bot_base_dir
        loaded_data = load_config(config_type="bot", base_dir=app_state.bot_base_dir)

        # 如果加载失败但没有抛出异常，提供更多信息
        if not loaded_data:
            print(f"[toml_form_generator] 警告：Bot 配置文件加载成功但为空")
        else:
            print(f"[toml_form_generator] 成功加载 Bot 配置，包含 {len(loaded_data)} 个顶级键")

        return loaded_data

    except FileNotFoundError as e:
        print(f"[toml_form_generator] Bot 配置文件未找到: {e}, 返回空字典")
        return {}
    except Exception as e:
        print(f"[toml_form_generator] 加载 Bot 配置文件时发生错误: {e}")
        import traceback

        traceback.print_exc()
        return {}

# Updated function signature
def create_toml_form(
    page: ft.Page,
    config_data: Dict[str, Any],
    container: ft.Column,
    template_filename: str = "bot_config_template.toml",
    save_callback: Optional[SaveCallback] = None, # Pass save callback
    debounce_interval: float = 1.0, # Default debounce interval
) -> TomlFormGenerator:
    """
    创建并构建TOML表单。

    Args:
        page: Flet Page 对象
        config_data: 要编辑的配置数据
        container: 放置表单控件的父容器
        template_filename: 要使用的模板文件名
        save_callback: 用于自动保存的回调函数
        debounce_interval: 自动保存防抖间隔

    Returns:
        创建的 TomlFormGenerator 实例
    """
    generator = TomlFormGenerator(
        page,
        config_data,
        container,
        template_filename,
        save_callback, # Pass callback
        debounce_interval,
    )
    generator.build_form()
    return generator # Return the instance
