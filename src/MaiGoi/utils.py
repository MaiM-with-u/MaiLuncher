import flet as ft
import os
import sys
import subprocess
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .state import AppState  # Avoid circular import for type hinting


async def update_page_safe(page: Optional[ft.Page]):
    """Safely call page.update() if the page object is valid."""
    if page:
        try:
            page.update()
        except Exception:
            # Reduce noise, perhaps only print if debug is enabled later
            # print(f"Error during safe page update: {e}")
            pass  # Silently ignore update errors, especially during shutdown


def show_snackbar(page: Optional[ft.Page], message: str, error: bool = False):
    """Helper function to display a SnackBar."""
    if not page:
        print(f"[Snackbar - No Page] {'Error' if error else 'Info'}: {message}")
        return
    try:
        page.snack_bar = ft.SnackBar(
            ft.Text(message),
            bgcolor=ft.colors.ERROR if error else None,
            open=True,
        )
        page.update()
    except Exception as e:
        print(f"Error showing snackbar: {e}")


def run_script(script_path: str, page: Optional["ft.Page"], app_state: Optional["AppState"], is_python: bool = False):
    """运行脚本文件(.bat或.py)，根据bot.py的目录位置来确定脚本位置。"""
    if not app_state:
        print("[run_script] Error: AppState not available.", flush=True)
        if page:
            show_snackbar(page, "错误：AppState不可用", error=True)
        return

    # 优先使用bot_base_dir作为脚本目录
    script_dir = None
    if hasattr(app_state, 'bot_base_dir') and app_state.bot_base_dir:
        script_dir = str(app_state.bot_base_dir)
        print(f"[run_script] 使用bot_base_dir作为脚本目录: {script_dir}", flush=True)
    elif hasattr(app_state, 'script_dir') and app_state.script_dir:
        script_dir = app_state.script_dir
        print(f"[run_script] 使用script_dir作为脚本目录: {script_dir}", flush=True)
    else:
        print("[run_script] Error: 无法确定脚本目录。", flush=True)
        if page:
            show_snackbar(page, "错误：无法确定脚本目录", error=True)
        return

    # 构建脚本的完整路径
    full_script_path = os.path.join(script_dir, script_path)
    print(f"[run_script] 尝试运行: {full_script_path}", flush=True)

    try:
        if not os.path.exists(full_script_path):
            print(f"[run_script] Error: 脚本文件未找到: {full_script_path}", flush=True)
            if page:
                show_snackbar(page, f"错误：脚本文件未找到\n{script_path}", error=True)
            return

        # --- 平台特定执行 --- #
        if sys.platform == "win32":
            if script_path.lower().endswith(".bat"):
                print("[run_script] 在Windows上使用'start cmd /k'运行.bat文件。", flush=True)
                # 使用start cmd /k保持脚本结束后窗口打开
                subprocess.Popen(f'start cmd /k "{full_script_path}"', shell=True, cwd=script_dir)
            elif script_path.lower().endswith(".py"):
                print("[run_script] 在Windows上使用Python解释器运行.py文件。", flush=True)
                # 使用当前解释器在新控制台窗口运行Python脚本
                # 使用sys.executable确保使用正确的Python环境
                subprocess.Popen(
                    f'start "Running {script_path}" "{sys.executable}" "{full_script_path}"',
                    shell=True,
                    cwd=script_dir,
                )
            else:
                print(
                    f"[run_script] 在Windows上尝试使用'start'运行未知类型文件: {script_path}",
                    flush=True,
                )
                # 尝试对其他文件类型使用通用start，可能会打开关联的程序
                subprocess.Popen(f'start "{full_script_path}"', shell=True, cwd=script_dir)
        else:  # Linux/macOS
            if script_path.lower().endswith(".py"):
                print("[run_script] 在非Windows上使用Python解释器运行.py文件。", flush=True)
                # 在类Unix系统上，我们通常需要终端模拟器来查看输出
                try:
                    subprocess.Popen(["xterm", "-e", sys.executable, full_script_path], cwd=script_dir)
                except FileNotFoundError:
                    print(
                        "[run_script] 未找到xterm。尝试直接运行Python（输出可能会丢失）。",
                        flush=True,
                    )
                    try:
                        subprocess.Popen([sys.executable, full_script_path], cwd=script_dir)
                    except Exception as e_direct:
                        print(f"[run_script] 直接运行Python脚本时出错: {e_direct}", flush=True)
                        if page:
                            show_snackbar(page, f"运行脚本时出错: {e_direct}", error=True)
                        return
            elif os.access(full_script_path, os.X_OK):  # 检查是否可执行
                print("[run_script] 在非Windows上直接运行可执行脚本。", flush=True)
                try:
                    subprocess.Popen([full_script_path], cwd=script_dir)
                except Exception as e_exec:
                    print(f"[run_script] 运行可执行脚本时出错: {e_exec}", flush=True)
                    if page:
                        show_snackbar(page, f"运行脚本时出错: {e_exec}", error=True)
                    return
            else:
                print(
                    f"[run_script] 不知道如何在非Windows上运行非可执行、非python脚本: {script_path}",
                    flush=True,
                )
                if page:
                    show_snackbar(page, f"无法运行此类型的文件: {script_path}", error=True)
                return

        if page:
            show_snackbar(page, f"正在尝试运行脚本: {script_path}")

    except Exception as e:
        print(f"[run_script] 运行脚本'{script_path}'时发生意外错误: {e}", flush=True)
        if page:
            show_snackbar(page, f"运行脚本时发生意外错误: {e}", error=True)
