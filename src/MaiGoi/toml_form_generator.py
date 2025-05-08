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
        config_metadata: Optional[Dict[str, Any]] = None, # 配置元数据
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
            config_metadata: 配置项的元数据信息
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
        self.config_metadata = config_metadata or {} # 存储元数据

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

    def _get_metadata(self, key_path: str) -> Dict[str, Any]:
        """获取指定键路径的元数据"""
        try:
            if not self.config_metadata:
                return {}
            
            # 直接尝试获取元数据
            if key_path in self.config_metadata:
                return self.config_metadata[key_path]
            
            # 如果找不到，尝试递归查找
            parts = key_path.split(".")
            current = self.config_metadata
            
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    # 如果找不到完整路径，尝试仅使用最后一部分
                    if len(parts) > 1 and parts[-1] in self.config_metadata:
                        return self.config_metadata[parts[-1]]
                    return {}
                
            # 如果找到的是字典并且包含元数据属性，返回它
            if isinstance(current, dict) and any(k in current for k in ["describe", "important", "can_edit"]):
                return current
            
            return {}
        except Exception as e:
            print(f"获取元数据出错: {key_path}, {e}")
            return {}

    def _get_comment(self, key_path: str) -> str:
        """获取指定键路径的注释，优先使用元数据中的描述"""
        try:
            # 首先尝试从元数据中获取描述
            metadata = self._get_metadata(key_path)
            if metadata and "describe" in metadata:
                return metadata["describe"]
            
            # 如果没有元数据描述，则从模板中获取注释
            comment = get_comment_for_key(self.template_doc, key_path)
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
            # 获取注释和元数据
            comment = self._get_comment(full_path)
            metadata = self._get_metadata(full_path)
            
            # 创建控件
            control = self._create_control_for_value(key, value, full_path)
            
            if control:
                # 创建控件容器
                control_container = ft.Column([control], tight=True)
                
                # 如果有描述，添加描述文本
                if comment:
                    description = ft.Text(
                        comment,
                        size=12,
                        color=ft.colors.SECONDARY,
                        italic=True,
                    )
                    control_container.controls.append(description)
                
                # 添加分隔线
                control_container.controls.append(ft.Divider(thickness=0.5))
                
                # 处理缩进
                if indent > 0:
                    row = ft.Row(
                        [
                            ft.Container(width=indent * 20),  # 每级缩进20像素
                            control_container,
                        ],
                        alignment=ft.MainAxisAlignment.START,
                    )
                    container.controls.append(row)
                else:
                    container.controls.append(control_container)

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
        """为配置值创建对应的控件"""
        # 获取注释和元数据
        comment = self._get_comment(full_path)
        metadata = self._get_metadata(full_path)
        
        # 检查是否可编辑
        can_edit = metadata.get("can_edit", True)
        important = metadata.get("important", False)
        
        # 根据值类型创建对应的控件
        if isinstance(value, bool):
            return self._create_boolean_control(key, value, full_path, comment, can_edit, important)
        elif isinstance(value, (int, float)):
            return self._create_number_control(key, value, full_path, comment, can_edit, important)
        elif isinstance(value, str):
            return self._create_string_control(key, value, full_path, comment, can_edit, important)
        elif isinstance(value, list):
            return self._create_list_control(key, value, full_path, comment, can_edit, important)
        elif isinstance(value, set):
            return self._create_set_control(key, value, full_path, comment, can_edit, important)
        return None

    def _create_boolean_control(self, key: str, value: bool, path: str, comment: str = "", can_edit: bool = True, important: bool = False) -> ft.Control:
        """创建布尔值控件"""
        control = ft.Switch(
            label=key,
            value=value,
            disabled=not can_edit,
            on_change=lambda e: self._update_config_value(path, e.control.value) if can_edit else None,
        )
        
        if comment:
            control.tooltip = comment
            
        if important:
            control.label_style = ft.TextStyle(weight=ft.FontWeight.BOLD)
            
        return control

    def _create_number_control(self, key: str, value: Union[int, float], path: str, comment: str = "", can_edit: bool = True, important: bool = False) -> ft.Control:
        """创建数字控件"""
        control = ft.TextField(
            label=key,
            value=str(value),
            disabled=not can_edit,
            on_change=lambda e: self._handle_number_change(path, e.control.value) if can_edit else None,
        )
        
        if comment:
            control.tooltip = comment
            
        if important:
            control.label_style = ft.TextStyle(weight=ft.FontWeight.BOLD)
            
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

    def _create_string_control(self, key: str, value: str, path: str, comment: str = "", can_edit: bool = True, important: bool = False) -> ft.Control:
        """创建字符串控件"""
        is_multiline = len(value) > 50 or "\n" in value # 检查是否应该多行
        
        control = ft.TextField(
            label=key,
            value=value,
            multiline=is_multiline,
            min_lines=1 if not is_multiline else 3,
            max_lines=1 if not is_multiline else 8,
            disabled=not can_edit,
            on_change=lambda e: self._update_config_value(path, e.control.value) if can_edit else None,
        )
        
        if comment:
            control.tooltip = comment
            
        if important:
            control.label_style = ft.TextStyle(weight=ft.FontWeight.BOLD)
        
        return control

    def _create_list_control(self, key: str, value: List[Any], path: str, comment: str = "", can_edit: bool = True, important: bool = False) -> ft.Control:
        """为列表类型创建控件 (修改以支持自动保存)"""
        items_column = ft.Column([]) # Column to hold list item controls
        list_item_controls = {} # Maps index to control

        def update_list_value():
            """更新配置数据中的列表值"""
            updated_list = []
            for i in range(len(list_item_controls)):
                if i in list_item_controls and list_item_controls[i]:
                    control = list_item_controls[i].controls[0] # Get the TextField
                    if hasattr(control, "value"):
                        try:
                            # Try to convert numbers if possible
                            item_value = control.value
                            try:
                                numeric_value = float(item_value)
                                if numeric_value.is_integer():
                                    item_value = int(numeric_value)
                                else:
                                    item_value = numeric_value
                            except:
                                pass # Not a number, keep as string
                            updated_list.append(item_value)
                        except Exception as e:
                            print(f"Error getting value for list item {i}: {e}")
            # Update the config data and trigger callback
            self._update_config_value(path, updated_list)

        def on_item_change(e):
            """Handle changes for any item in the list"""
            if can_edit:
                update_list_value()

        # 创建标题和添加按钮行
        header_controls = [
            ft.Text(key, weight=ft.FontWeight.BOLD),
        ]
        
        # 仅在可编辑时添加按钮
        if can_edit:
            add_button = ft.IconButton(
                icon=ft.icons.ADD,
                tooltip="添加新项",
                on_click=lambda e: add_item(),
            )
            header_controls.append(add_button)
        
        # 如果有注释，添加一个Info图标
        if comment:
            info_button = ft.IconButton(
                icon=ft.icons.INFO_OUTLINE,
                tooltip=comment,
                icon_size=16
            )
            header_controls.insert(1, info_button) # 在文本后、添加按钮前插入
            
        if important:
            header_controls[0] = ft.Text(key, weight=ft.FontWeight.BOLD, color=ft.colors.PRIMARY)
        
        header_row = ft.Row(header_controls, alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        def delete_item(e):
            """Deletes an item from the list UI and triggers update."""
            if not can_edit:
                return
            
            row_to_delete = e.control.data # Get the Row containing this button
            if row_to_delete in items_column.controls:
                index_to_delete = items_column.controls.index(row_to_delete)
                items_column.controls.remove(row_to_delete)
                
                # Update our control map - shift all items after this one up
                new_control_map = {}
                for idx, control in list_item_controls.items():
                    if idx < index_to_delete:
                        new_control_map[idx] = control
                    elif idx > index_to_delete:
                        new_control_map[idx-1] = control
                
                list_item_controls.clear()
                list_item_controls.update(new_control_map)
                
                update_list_value() # Update the stored list value
                self.page.update() # Update UI immediately

        def add_item(e=None, item_value="", is_initial=False):
            """Adds a new item to the list UI (empty or with preset value)"""
            if not can_edit and not is_initial:
                return
            
            next_index = len(items_column.controls)
            
            # Create a row with TextField and delete button
            item_controls = []
            
            # 创建文本框
            item_field = ft.TextField(
                value=str(item_value),
                expand=True,
                on_change=on_item_change,
                disabled=not can_edit,
            )
            item_controls.append(item_field)
            
            # 仅在可编辑时添加删除按钮
            if can_edit:
                delete_button = ft.IconButton(
                    icon=ft.icons.DELETE_OUTLINE,
                    on_click=delete_item,
                    tooltip="删除此项",
                )
                item_controls.append(delete_button)
            
            item_row = ft.Row(item_controls, alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            
            # Store a reference to the delete button's parent row
            if can_edit and len(item_controls) > 1:
                item_controls[1].data = item_row
            
            # Add to our UI and control map
            items_column.controls.append(item_row)
            list_item_controls[next_index] = item_row
            
            if not is_initial:
                self.page.update() # Update UI immediately
                update_list_value() # Update the stored list

        # Populate with existing items
        for item in value:
            add_item(item_value=item, is_initial=True)

        # Assemble the container for the whole list control
        list_container = ft.Column([
            header_row,
            items_column,
        ])

        return list_container

    def _create_set_control(self, key: str, value: set, path: str, comment: str = "", can_edit: bool = True, important: bool = False) -> ft.Control:
        """为集合类型创建控件 (修改以支持自动保存)"""
        items_column = ft.Column([], spacing=2, scroll=ft.ScrollMode.ADAPTIVE)
        set_item_controls = {} # Maps text value to Row control

        def update_set_value():
            """Update config with current set items"""
            current_values = set(set_item_controls.keys())
            self._update_config_value(path, current_values)

        def delete_item(e):
            """Deletes an item from the set UI and triggers update."""
            if not can_edit:
                return
            
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
            """Adds item from text field or directly from provided text"""
            if not can_edit and not item_text:
                return
            
            # Get the text either from event or parameter
            text_to_add = item_text
            if not text_to_add and e and hasattr(e, "control") and hasattr(e.control, "value"):
                text_to_add = e.control.value.strip()
            
            if not text_to_add:
                return # Skip empty items
            
            # Skip if this exact text is already in the set
            if text_to_add in set_item_controls:
                print(f"Item already exists in set: {text_to_add}")
                return
            
            # Create a row with the item text and a delete button
            item_display = ft.Text(text_to_add, size=14)
            delete_btn = ft.IconButton(
                icon=ft.icons.DELETE_OUTLINE,
                tooltip="删除此项",
                on_click=delete_item,
            )
            item_row = ft.Row(
                [
                    item_display,
                    delete_btn,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            
            # Store reference to row for deletion handler
            delete_btn.data = item_row
            
            # Add to our maps and UI
            items_column.controls.append(item_row)
            set_item_controls[text_to_add] = item_row
            
            # If coming from text field, clear it
            if e and hasattr(e, "control") and hasattr(e.control, "value"):
                e.control.value = ""
            
            # Update data and UI
            if not item_text: # Only update if not initial load
                update_set_value()
                self.page.update()

        # Create add item fields
        input_field = ft.TextField(
            hint_text="添加新项...",
            expand=True,
            disabled=not can_edit,
        )
        
        add_button = ft.IconButton(
            icon=ft.icons.ADD,
            on_click=lambda e: add_item_from_field(e),
            disabled=not can_edit,
        )
        
        # 添加 key_down 事件，可以按 Enter 添加
        if can_edit:
            input_field.on_submit = lambda e: add_item_from_field(e)
        
        input_row = ft.Row(
            [input_field, add_button],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # Populate existing items
        for item in value:
            add_item_from_field(item_text=str(item)) # Add initial items

        # Create header row
        header_controls = [
            ft.Text(key, weight=ft.FontWeight.BOLD),
        ]
        
        # 如果有注释，添加一个Info图标
        if comment:
            info_button = ft.IconButton(
                icon=ft.icons.INFO_OUTLINE,
                tooltip=comment,
                icon_size=16
            )
            header_controls.append(info_button)
            
        if important:
            header_controls[0] = ft.Text(key, weight=ft.FontWeight.BOLD, color=ft.colors.PRIMARY)
        
        header_row = ft.Row(
            header_controls, 
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )

        # 组装完整容器
        input_section = ft.Column([input_row]) if can_edit else ft.Column([])
        
        set_container = ft.Column([
            header_row,
            items_column,
            input_section,
        ])

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
    config_metadata: Optional[Dict[str, Any]] = None, # 配置元数据
) -> TomlFormGenerator:
    """创建TOML表单生成器实例"""
    generator = TomlFormGenerator(
        page=page,
        config_data=config_data,
        parent_container=container,
        template_filename=template_filename,
        save_callback=save_callback,
        debounce_interval=debounce_interval,
        config_metadata=config_metadata, # 传递元数据
    )
    generator.build_form()
    return generator
