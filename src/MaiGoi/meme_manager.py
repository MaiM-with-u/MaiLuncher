import flet as ft
from pathlib import Path
import os
import shutil
from typing import TYPE_CHECKING
from bson import ObjectId # Import ObjectId for querying by _id
import re # <-- Import the regular expression module
import uuid # 用于生成唯一文件名
import hashlib
from PIL import Image
import io
import time

if TYPE_CHECKING:
    from .state import AppState
    from pymongo.database import Database # For type hinting app_state.gui_db

# Attempt to import get_asset_path from ui_views. This creates a potential circular dependency
# if ui_views also imports meme_manager. A better approach might be to move get_asset_path
# to a common utils module if it's widely used, or pass mmc_path directly.
# For now, we'll try a guarded import or pass necessary pathing info.
try:
    from .ui_views import get_asset_path, TEXT_LIGHT_COLOR # Assuming TEXT_LIGHT_COLOR is also needed
except ImportError:
    # Fallback or error if direct import isn't feasible/clean
    print("[MemeManager] Warning: Could not import get_asset_path or TEXT_LIGHT_COLOR from ui_views directly.")
    # Define a simple fallback for TEXT_LIGHT_COLOR if needed, or ensure it's passed
    TEXT_LIGHT_COLOR = ft.colors.with_opacity(0.7, ft.colors.ON_SURFACE)
    def get_asset_path(relative_path: str) -> str: # Basic fallback
        # This basic fallback won't handle sys.frozen like the original one.
        # It's better to ensure the original is accessible or its logic replicated if needed.
        return relative_path

# --- Helper function for splitting emotion strings --- #
def _split_emotion_string(input_string: str) -> list[str]:
    """Splits a string by English or Chinese comma, trims whitespace, and removes empty strings."""
    if not input_string:
        return []
    # Split by English comma, Chinese comma, and optional surrounding whitespace
    split_items = re.split(r'\s*[,，]\s*', input_string)
    # Filter out empty strings that might result from consecutive commas or leading/trailing commas
    return [item.strip() for item in split_items if item.strip()]

def load_memes_from_db(app_state: "AppState"):
    """Fetches meme data from the MongoDB 'emoji' collection."""
    if not app_state.gui_db:
        print("[MemeManager] Error: Database connection not available in AppState.")
        return []

    try:
        emoji_collection = app_state.gui_db.emoji 
        memes = list(emoji_collection.find()) 
        print(f"[MemeManager] Loaded {len(memes)} memes from the database.")
        # --- 添加日志：打印前几个表情包的 emotion 字段 --- #
        if memes:
            print("[MemeManager Debug] First few loaded emotion fields:")
            for i, meme in enumerate(memes[:3]): # 只打印前3个作为示例
                emotion_data = meme.get("emotion", "<Emotion field missing>")
                print(f"  - Meme {i+1} (_id: {meme.get('_id')}) -> emotion type: {type(emotion_data)}, value: {emotion_data}")
        # --- 日志结束 --- #
        return memes
    except Exception as e:
        print(f"[MemeManager] Error loading memes from database: {e}")
        return []

def update_meme_description_in_db(app_state: "AppState", meme_id: str, new_description: str):
    """Updates the description of a specific meme in the database."""
    if not app_state.gui_db:
        print("[MemeManager] Error: Database connection not available for update.")
        return False, "数据库未连接"

    try:
        emoji_collection = app_state.gui_db.emoji
        result = emoji_collection.update_one(
            {"_id": ObjectId(meme_id)}, # Query by ObjectId
            {"$set": {"description": new_description}}
        )
        if result.modified_count > 0:
            print(f"[MemeManager] Meme ID {meme_id} description updated successfully.")
            return True, "描述已更新"
        elif result.matched_count > 0:
            print(f"[MemeManager] Meme ID {meme_id} found, but description was already the same.")
            return True, "描述未更改"
        else:
            print(f"[MemeManager] Error: Meme ID {meme_id} not found for update.")
            return False, "未找到表情包"
    except Exception as e:
        print(f"[MemeManager] Error updating meme description in DB: {e}")
        return False, f"数据库更新失败: {e}"

def update_meme_emotions_in_db(app_state: "AppState", meme_id: str, new_emotions: list[str]):
    """Updates the emotions list of a specific meme in the database."""
    if not app_state.gui_db:
        print("[MemeManager] Error: Database connection not available for emotion update.")
        return False, "数据库未连接"
    try:
        emoji_collection = app_state.gui_db.emoji
        result = emoji_collection.update_one(
            {"_id": ObjectId(meme_id)},
            {"$set": {"emotion": new_emotions}} # Replace the entire emotion array
        )
        if result.modified_count > 0:
            print(f"[MemeManager] Meme ID {meme_id} emotions updated successfully.")
            return True, "情绪已更新"
        elif result.matched_count > 0:
            print(f"[MemeManager] Meme ID {meme_id} found, but emotions might be the same or no change made.")
            # It's harder to tell if a list is "the same" without more complex checks, so we simplify
            return True, "情绪数据已提交"
        else:
            print(f"[MemeManager] Error: Meme ID {meme_id} not found for emotion update.")
            return False, "未找到表情包"
    except Exception as e:
        print(f"[MemeManager] Error updating meme emotions in DB: {e}")
        return False, f"数据库更新失败: {e}"

def add_meme_to_db(app_state: "AppState", image_file_path: str, description: str, emotions: list[str]):
    """添加新表情包到数据库和MMC文件夹。
    
    Args:
        app_state: 应用状态对象
        image_file_path: 源图片的路径
        description: 表情包描述
        emotions: 表情包相关的情绪标签列表
        
    Returns:
        tuple: (success, message)
    """
    if not app_state.gui_db:
        print("[MemeManager] Error: Database connection not available for add.")
        return False, "数据库未连接"
    
    try:
        # 1. 生成目标路径（MMC文件夹内）
        source_path = Path(image_file_path)
        if not source_path.exists():
            return False, "找不到源图片"
        
        # 生成唯一文件名，保留原始扩展名
        unique_filename = f"{uuid.uuid4().hex}{source_path.suffix}"
        
        # 检查MMC路径是否存在
        mmc_path = Path(app_state.mmc_path)
        if not mmc_path.exists():
            return False, "无法找到MMC文件夹"
        
        # 创建相对路径结构 (注意这应该与现有表情包的存储方式一致)
        relative_path = f"imgs/{unique_filename}"
        target_path = mmc_path / "imgs"
        
        # 确保目标文件夹存在
        if not target_path.exists():
            target_path.mkdir(parents=True, exist_ok=True)
            
        # 2. 复制图片到MMC文件夹
        target_file = target_path / unique_filename
        shutil.copy2(source_path, target_file)
        
        # 3. 计算图片哈希值和获取图片格式
        # 读取图片字节
        with open(target_file, "rb") as img_file:
            img_bytes = img_file.read()
            # 计算MD5哈希值
            img_hash = hashlib.md5(img_bytes).hexdigest()
            
        # 获取图片格式
        with Image.open(target_file) as img:
            img_format = img.format.lower() if img.format else ""
        
        # 当前时间戳
        current_time = int(time.time())
        
        # 4. 添加记录到数据库
        emoji_collection = app_state.gui_db.emoji
        new_meme = {
            "filename": unique_filename,
            "path": str(target_path),
            "full_path": relative_path,
            "description": description,
            "emotion": emotions,
            "hash": img_hash,
            "format": img_format,
            "timestamp": current_time,   # 注册时间
            "last_used_time": current_time,  # 最后使用时间，初始与注册时间相同
            "usage_count": 0,            # 使用次数，初始为0
            "embedding": []              # 暂时为空，如需向量嵌入可扩展
        }
        
        result = emoji_collection.insert_one(new_meme)
        if result.inserted_id:
            print(f"[MemeManager] Added new meme with ID: {result.inserted_id}, hash: {img_hash}")
            return True, "表情包添加成功"
        else:
            # 如果插入失败，删除已复制的文件
            if target_file.exists():
                target_file.unlink()
            return False, "数据库插入失败"
            
    except Exception as e:
        print(f"[MemeManager] Error adding meme to database: {e}")
        # 尝试清理可能已复制的文件
        try:
            if 'target_file' in locals() and target_file.exists():
                target_file.unlink()
        except:
            pass
        return False, f"添加表情包失败: {e}"

def delete_meme_from_db(app_state: "AppState", meme_id: str):
    """从数据库中删除表情包，并可选择性地删除对应图片文件
    
    Args:
        app_state: 应用状态对象
        meme_id: 表情包在数据库中的ID
        
    Returns:
        tuple: (success, message)
    """
    if not app_state.gui_db:
        print("[MemeManager] Error: Database connection not available for delete.")
        return False, "数据库未连接"
    
    try:
        # 1. 首先获取表情包信息，确保我们有文件路径
        emoji_collection = app_state.gui_db.emoji
        meme_doc = emoji_collection.find_one({"_id": ObjectId(meme_id)})
        
        if not meme_doc:
            return False, "未找到表情包"
        
        # 2. 获取文件路径
        file_path = meme_doc.get("full_path")
        
        # 3. 从数据库中删除记录
        result = emoji_collection.delete_one({"_id": ObjectId(meme_id)})
        
        if result.deleted_count > 0:
            print(f"[MemeManager] Meme ID {meme_id} deleted from database.")
            
            # 4. 尝试删除文件（如果存在）
            if file_path:
                full_file_path = Path(app_state.mmc_path) / file_path
                if full_file_path.exists():
                    try:
                        full_file_path.unlink()
                        print(f"[MemeManager] Deleted file: {full_file_path}")
                    except Exception as file_e:
                        print(f"[MemeManager] Warning: Could not delete file {full_file_path}: {file_e}")
                        # 注意：我们仍然认为操作成功，因为数据库中的记录已被删除
            
            return True, "表情包已删除"
        else:
            return False, "数据库删除失败"
            
    except Exception as e:
        print(f"[MemeManager] Error deleting meme from database: {e}")
        return False, f"删除表情包失败: {e}"

def create_meme_card(meme_doc: dict, page: ft.Page, app_state: "AppState", on_update_refresh_grid):
    """Creates an ft.Card for a single meme document from the database.
       Includes an edit button to modify the description and emotions.
       on_update_refresh_grid: A callback function to refresh the grid after an update.
    """
    
    meme_id = str(meme_doc.get("_id")) 
    img_full_path_str = meme_doc.get("full_path")
    current_description = meme_doc.get("description", "No description")
    raw_emotions_from_db = meme_doc.get("emotion", []) 

    # --- Process raw emotions from DB using the helper function --- #
    processed_emotions = []
    for item in raw_emotions_from_db:
        if isinstance(item, str):
            # Use the helper function here
            processed_emotions.extend(_split_emotion_string(item))
        # Consider adding handling for non-string items if necessary
    
    current_emotions = sorted(list(set(processed_emotions)))
    print(f"[MemeCard Debug] Processed emotions for _id {meme_id}: {current_emotions}")

    # --- Edit Dialog Elements & State --- # 
    description_field_ref = ft.Ref[ft.TextField]()
    new_emotion_input_ref = ft.Ref[ft.TextField]()
    emotions_chip_row_ref = ft.Ref[ft.Row]()
    edited_emotions_in_dialog = [] 

    def close_dialog(e=None):
        if edit_dialog:
            edit_dialog.open = False
            page.update()
    
    def _update_emotion_chips_ui():
        nonlocal edited_emotions_in_dialog 
        if emotions_chip_row_ref.current:
            chips = []
            for index, emo in enumerate(edited_emotions_in_dialog):
                chips.append(
                    ft.Chip(
                        label=ft.Text(emo),
                        delete_icon_tooltip=f"删除情绪 '{emo}'",
                        on_delete=lambda e, idx=index, emotion_to_delete=emo: delete_emotion(idx, emotion_to_delete), 
                    )
                )
            emotions_chip_row_ref.current.controls = chips
            # No direct update here

    def add_new_emotion(e):
        nonlocal edited_emotions_in_dialog
        input_value = new_emotion_input_ref.current.value.strip()
        
        if not input_value:
            new_emotion_input_ref.current.error_text = "情绪不能为空"
            new_emotion_input_ref.current.update()
            return
        
        # Use the helper function to split the input
        potential_new_emotions = _split_emotion_string(input_value)
        
        print(f"[MemeManager Debug] add_new_emotion - Split result: {potential_new_emotions}")
        
        added_count = 0
        for new_emo in potential_new_emotions:
            # Stripping is already done by the helper function, but check again for safety?
            # emo_stripped = new_emo # No need to strip again if helper does it
            if new_emo and new_emo not in edited_emotions_in_dialog:
                edited_emotions_in_dialog.append(new_emo)
                added_count += 1
        
        if added_count > 0:
            _update_emotion_chips_ui() 
            new_emotion_input_ref.current.value = "" 
            new_emotion_input_ref.current.error_text = None
            new_emotion_input_ref.current.update()
            if edit_dialog and edit_dialog.content: edit_dialog.content.update()
        elif potential_new_emotions: 
            new_emotion_input_ref.current.error_text = "输入的情绪已存在"
            new_emotion_input_ref.current.update()

    def delete_emotion(index_to_delete, emotion_name):
        nonlocal edited_emotions_in_dialog
        try:
            if 0 <= index_to_delete < len(edited_emotions_in_dialog) and edited_emotions_in_dialog[index_to_delete] == emotion_name:
                del edited_emotions_in_dialog[index_to_delete]
            else: 
                edited_emotions_in_dialog.remove(emotion_name)
            _update_emotion_chips_ui() 
            if edit_dialog and edit_dialog.content: edit_dialog.content.update()
        except ValueError:
            print(f"Error: Emotion '{emotion_name}' not found in list for deletion.")
        except Exception as ex:
            print(f"Error deleting emotion: {ex}")

    def save_changes(e):
        nonlocal edited_emotions_in_dialog 
        new_desc = description_field_ref.current.value if description_field_ref.current else ""
        if not new_desc.strip():
            description_field_ref.current.error_text = "描述不能为空"
            description_field_ref.current.update()
            return
        else:
            description_field_ref.current.error_text = None
            description_field_ref.current.update()
        final_emotions_list = sorted(edited_emotions_in_dialog)
        desc_success, desc_message = True, ""
        if new_desc != current_description:
            desc_success, desc_message = update_meme_description_in_db(app_state, meme_id, new_desc)
        emo_success, emo_message = True, ""
        if final_emotions_list != current_emotions: # Compare against processed & sorted list
            emo_success, emo_message = update_meme_emotions_in_db(app_state, meme_id, final_emotions_list)
        if desc_success and emo_success:
            on_update_refresh_grid()
            close_dialog()
            final_message = "更改已保存"
            if desc_message and desc_message not in ["描述未更改", "描述已更新"]: final_message = desc_message
            if emo_message and emo_message not in ["情绪数据已提交", "情绪已更新"]:
                final_message = f"{final_message}; {emo_message}" if final_message != "更改已保存" else emo_message
            elif desc_message == "描述已更新" and emo_message == "情绪已更新": final_message = "描述和情绪已更新"
            elif desc_message == "描述已更新": final_message = "描述已更新"
            elif emo_message == "情绪已更新": final_message = "情绪已更新"
            show_snackbar(page, final_message)
        else:
            error_msg = f"{desc_message if not desc_success else ''} {emo_message if not emo_success else ''}".strip()
            show_snackbar(page, error_msg if error_msg else "保存失败", error=True)
    
    # 处理删除表情包
    def delete_meme(e):
        # 创建确认对话框
        confirm_dialog = ft.AlertDialog(
            title=ft.Text("确认删除"),
            content=ft.Text("确定要删除此表情包吗？此操作不可撤销。"),
            actions=[
                ft.TextButton("取消", on_click=lambda e: close_confirm_dialog()),
                ft.ElevatedButton(
                    "删除", 
                    on_click=lambda e: confirm_delete_meme(),
                    bgcolor=ft.colors.ERROR,
                    color=ft.colors.WHITE,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        def close_confirm_dialog():
            page.dialog = confirm_dialog
            confirm_dialog.open = False
            page.update()
            
        def confirm_delete_meme():
            close_confirm_dialog()
            success, message = delete_meme_from_db(app_state, meme_id)
            if success:
                # 刷新表情包网格
                on_update_refresh_grid()
                show_snackbar(page, message)
            else:
                show_snackbar(page, message, error=True)
        
        # 显示确认对话框
        page.dialog = confirm_dialog
        confirm_dialog.open = True
        page.update()
    
    edit_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("编辑表情包信息"),
        content=ft.Column([
            ft.TextField(
                ref=description_field_ref, label="表情包描述", value=current_description,
                multiline=True, min_lines=3, max_lines=5, keyboard_type=ft.KeyboardType.MULTILINE,
            ),
            ft.Divider(height=15, color=ft.colors.OUTLINE_VARIANT),
            ft.Text("情绪标签:", weight=ft.FontWeight.BOLD),
            ft.Row(ref=emotions_chip_row_ref, wrap=True, spacing=5, run_spacing=5),
            ft.Row([
                ft.TextField(ref=new_emotion_input_ref, label="新情绪", hint_text="输入后按 Enter 或点击添加", expand=True, on_submit=add_new_emotion),
                ft.IconButton(ft.icons.ADD_CIRCLE_OUTLINE, tooltip="添加情绪", on_click=add_new_emotion)
            ], spacing=10)
        ], scroll=ft.ScrollMode.ADAPTIVE),
        actions=[
            ft.TextButton("取消", on_click=close_dialog),
            ft.ElevatedButton("保存更改", on_click=save_changes, autofocus=True),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    def open_edit_dialog(e):
        nonlocal edited_emotions_in_dialog
        if edit_dialog not in page.overlay: page.overlay.append(edit_dialog)
        if description_field_ref.current: description_field_ref.current.value = current_description
        # Initialize dialog state with the processed list from DB
        edited_emotions_in_dialog = list(current_emotions)
        _update_emotion_chips_ui()
        if new_emotion_input_ref.current: new_emotion_input_ref.current.value = ""
        edit_dialog.open = True
        page.update()

    actual_img_path = None
    if img_full_path_str:
        prospective_path = Path(app_state.mmc_path) / img_full_path_str
        if prospective_path.exists() and prospective_path.is_file():
            actual_img_path = str(prospective_path)
        else:
            print(f"[MemeCard] Warning: Meme image not found at {prospective_path}")
            placeholder_path_str = get_asset_path("src/MaiGoi/assets/placeholder_image.png")
            if Path(placeholder_path_str).exists(): actual_img_path = placeholder_path_str
            else: print(f"[MemeCard] Critical: Placeholder not found at {placeholder_path_str}")

    emotion_text_display = ", ".join(current_emotions) if current_emotions else "-"

    description_text_ref = ft.Ref[ft.Text]() 
    emotion_text_widget_ref = ft.Ref[ft.Text]() 

    card_content_list = [
        ft.Container(
            content=ft.Image(src=actual_img_path if actual_img_path else "", width=150, height=150, fit=ft.ImageFit.CONTAIN, border_radius=ft.border_radius.all(8))
            if actual_img_path else ft.Container(width=150, height=150, bgcolor=ft.colors.OUTLINE_VARIANT, content=ft.Text("无图", text_align=ft.TextAlign.CENTER, weight=ft.FontWeight.BOLD), alignment=ft.alignment.center, border_radius=ft.border_radius.all(8)),
            padding=ft.padding.all(5), alignment=ft.alignment.center,
        ),
        ft.Row([
            ft.Text(current_description, ref=description_text_ref, size=11, text_align=ft.TextAlign.LEFT, color=TEXT_LIGHT_COLOR, max_lines=3, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
            ft.IconButton(ft.icons.EDIT_OUTLINED, icon_size=16, tooltip="编辑信息", on_click=open_edit_dialog),
            ft.IconButton(ft.icons.DELETE_OUTLINE, icon_size=16, tooltip="删除表情包", on_click=delete_meme, icon_color=ft.colors.ERROR)
        ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.START),
        ft.Container( 
            content=ft.Text(f"情绪: {emotion_text_display}", ref=emotion_text_widget_ref, size=10, text_align=ft.TextAlign.LEFT, color=TEXT_LIGHT_COLOR, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, tooltip=f"情绪: {emotion_text_display}"),
            padding=ft.padding.symmetric(horizontal=8, vertical=2), width=160,
        )
    ]
    
    return ft.Card(
        content=ft.Column(card_content_list, spacing=4, alignment=ft.MainAxisAlignment.START, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        width=180, height=280, elevation=2,
    )

# --- Snackbar Utility (should ideally be in a common utils.py) --- #
def show_snackbar(page: ft.Page, message: str, error: bool = False, duration: int = 3000):
    print(f"[Snackbar] Attempting to show: '{message}'. Page object type: {type(page)}, Is Page instance: {isinstance(page, ft.Page)}")
    try:
        snackbar_color = ft.colors.RED_ACCENT_700 if error else ft.colors.GREEN_ACCENT_700
        snackbar_instance = ft.SnackBar(
            ft.Text(message, color=ft.colors.WHITE), 
            bgcolor=snackbar_color,
            open=True, # Open by default when shown
            duration=duration
        )
        
        # Check if the method exists before calling
        if hasattr(page, 'show_snack_bar') and callable(page.show_snack_bar):
            print("[Snackbar] Using page.show_snack_bar method.")
            page.show_snack_bar(snackbar_instance)
            # No need to call page.update() here, show_snack_bar handles it.
            print("[Snackbar] page.show_snack_bar called.")
        elif hasattr(page, 'overlay') and hasattr(page, 'update'):
             print("[Snackbar] Warning: page.show_snack_bar not found or not callable. Trying page.overlay.append...")
             # Fallback: Add manually to overlay (less common now but was used in older versions/specific cases)
             if snackbar_instance not in page.overlay:
                 page.overlay.append(snackbar_instance)
             page.update() # Need to update page after adding to overlay
             # Might need snackbar_instance.update() too, depending on Flet version nuances
             print("[Snackbar] Snackbar added to overlay and page updated.")
        else:
             print(f"[Snackbar] Error: Page object lacks expected methods (show_snack_bar or overlay/update). Cannot display snackbar.")

    except AttributeError as ae:
        print(f"[Snackbar] AttributeError showing snackbar: {ae}. This might indicate an issue with the page object state.")
        # import traceback
        # traceback.print_exc() # Uncomment for full traceback if needed
    except Exception as e:
        print(f"[Snackbar] Unexpected error showing snackbar: {e}")
        # import traceback
        # traceback.print_exc() # Uncomment for full traceback if needed

def build_meme_grid(page: ft.Page, app_state: "AppState"):
    """Builds the GridView control with meme cards loaded from the database."""
    
    grid_view_ref = ft.Ref[ft.GridView]() # Ref for the GridView itself

    def refresh_grid_content():
        print("[MemeManager] Refreshing meme grid content...")
        memes_from_db = load_memes_from_db(app_state)
        if not memes_from_db:
            # Handle empty or error case (e.g., show a message)
            if grid_view_ref.current:
                grid_view_ref.current.controls = [
                    ft.Column([
                        ft.Text("未能从数据库加载表情包，或数据库为空。", size=16, weight=ft.FontWeight.BOLD),
                        ft.Text("请检查数据库连接和 'emoji' 集合。", size=14)],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        alignment=ft.MainAxisAlignment.CENTER, expand=True, spacing=10
                    )
                ]
        else:
            # Pass the refresh_grid_content itself as the callback to create_meme_card
            new_cards_ui = [create_meme_card(meme_doc, page, app_state, refresh_grid_content) for meme_doc in memes_from_db]
            if grid_view_ref.current:
                grid_view_ref.current.controls = new_cards_ui
        
        if grid_view_ref.current:
             grid_view_ref.current.update()
        page.update() # Also update the page to reflect GridView changes
    
    # --- 添加表情包对话框 --- #
    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)
    
    description_input_ref = ft.Ref[ft.TextField]()
    emotions_input_ref = ft.Ref[ft.TextField]()
    selected_file_path_ref = ft.Ref[ft.Text]()
    
    def file_picker_result(e: ft.FilePickerResultEvent):
        # 处理文件选择结果
        if e.files:
            selected_file = e.files[0]
            selected_file_path_ref.current.value = selected_file.path
            selected_file_path_ref.current.visible = True
            selected_file_path_ref.current.update()

    # 设置文件选择器回调
    file_picker.on_result = file_picker_result
    
    def pick_image(e):
        file_picker.pick_files(
            dialog_title="选择表情包图片",
            allowed_extensions=["png", "jpg", "jpeg", "gif"],
            allow_multiple=False
        )
    
    def close_add_dialog(e=None):
        if add_meme_dialog:
            add_meme_dialog.open = False
            # 清空输入内容
            if description_input_ref.current:
                description_input_ref.current.value = ""
            if emotions_input_ref.current:
                emotions_input_ref.current.value = ""
            if selected_file_path_ref.current:
                selected_file_path_ref.current.value = ""
                selected_file_path_ref.current.visible = False
            page.update()
    
    def save_new_meme(e):
        # 验证输入
        if not selected_file_path_ref.current or not selected_file_path_ref.current.value:
            show_snackbar(page, "请选择图片文件", error=True)
            return
            
        description = description_input_ref.current.value.strip()
        if not description:
            description_input_ref.current.error_text = "描述不能为空"
            description_input_ref.current.update()
            return
        else:
            description_input_ref.current.error_text = None
            
        # 处理情绪标签
        emotions_input = emotions_input_ref.current.value.strip()
        emotions_list = _split_emotion_string(emotions_input) if emotions_input else []
        
        # 添加到数据库
        success, message = add_meme_to_db(
            app_state, 
            selected_file_path_ref.current.value,
            description,
            emotions_list
        )
        
        if success:
            close_add_dialog()
            refresh_grid_content()  # 刷新表情包网格
            show_snackbar(page, message)
        else:
            show_snackbar(page, message, error=True)
    
    # 创建添加表情包对话框
    add_meme_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("添加新表情包"),
        content=ft.Column([
            ft.ElevatedButton("选择图片", icon=ft.icons.IMAGE, on_click=pick_image),
            ft.Text("", ref=selected_file_path_ref, visible=False, size=12, color=TEXT_LIGHT_COLOR),
            ft.TextField(
                ref=description_input_ref, 
                label="表情包描述", 
                hint_text="输入这个表情包的描述",
                multiline=True, 
                min_lines=2, 
                max_lines=3
            ),
            ft.TextField(
                ref=emotions_input_ref,
                label="情绪标签",
                hint_text="输入情绪标签，用逗号分隔",
            ),
        ], scroll=ft.ScrollMode.AUTO, spacing=10),
        actions=[
            ft.TextButton("取消", on_click=close_add_dialog),
            ft.ElevatedButton("保存", on_click=save_new_meme),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    
    def open_add_dialog(e):
        if add_meme_dialog not in page.overlay:
            page.overlay.append(add_meme_dialog)
        add_meme_dialog.open = True
        page.update()

    # Initial build
    memes_from_db_initial = load_memes_from_db(app_state)
    if not memes_from_db_initial:
        return ft.Column(
            # ... (error/empty message as before) ...
             [
                ft.Text("未能从数据库加载表情包，或数据库为空。", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("请检查数据库连接和 'emoji' 集合。", size=14)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER, expand=True, spacing=10
        )
    
    # Pass refresh_grid_content as the callback here for initial card creation too
    initial_meme_cards_ui = [create_meme_card(meme_doc, page, app_state, refresh_grid_content) for meme_doc in memes_from_db_initial]
    
    # 创建一个Stack来包含GridView和浮动按钮
    return ft.Stack(
        [
            ft.GridView(
                ref=grid_view_ref, # Assign ref to the GridView
                runs_count=5, 
                max_extent=200, 
                child_aspect_ratio=180/280, 
                spacing=10,
                run_spacing=10,
                padding=ft.padding.all(20),
                controls=initial_meme_cards_ui,
                expand=True,
            ),
            # 添加浮动按钮
            ft.Container(
                content=ft.FloatingActionButton(
                    icon=ft.icons.ADD,
                    text="添加表情包",
                    on_click=open_add_dialog,
                    bgcolor=ft.colors.SECONDARY,
                ),
                bottom=20,
                right=20,
            ),
        ],
        expand=True,
    ) 