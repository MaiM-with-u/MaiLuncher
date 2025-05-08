import flet as ft
import subprocess
import threading
import os
from pathlib import Path
import time
import json
import requests
import shutil

class MMCDownloader:
    def __init__(self, page: ft.Page, on_close_callback=None):
        print("MMCDownloader 初始化开始...")
        self.page = page
        self.on_close_callback = on_close_callback
        self.repo_url_github = "https://github.com/MaiM-with-u/MaiBot.git"
        self.repo_url_gitee = "https://gitee.com/DrSmooth/MaiBot.git"
        self.repo_url = self.repo_url_github
        self.branches = []
        self.download_path = ""
        self.process = None
        self.log_output = []
        
        print("创建UI组件...")
        # 新增下载源选择下拉框
        self.source_dropdown = ft.Dropdown(
            label="选择下载源",
            width=200,
            options=[
                ft.dropdown.Option("github", text="GitHub"),
                ft.dropdown.Option("gitee", text="Gitee")
            ],
            value="github",
            on_change=self._on_source_change
        )
        # 组件
        self.branch_dropdown = ft.Dropdown(
            label="选择分支",
            width=200,
            disabled=True,
            hint_text="加载分支列表中...",
        )
        
        self.path_text = ft.TextField(
            label="下载路径",
            width=300,
            value=str(Path.cwd() / "mmcs"),
            hint_text="选择MMC的下载位置"
        )
        
        self.project_name_text = ft.TextField(
            label="MMC文件夹名",
            width=200,
            value="",
            hint_text="请输入本次下载的文件夹名"
        )
        
        self.status_text = ft.Text("准备就绪，请选择分支和下载路径", color=ft.Colors.PRIMARY)
        
        self.log_area = ft.ListView(
            expand=True,
            spacing=5,
            auto_scroll=True,
            height=200,
        )
        
        # 进度指示器
        self.progress_ring = ft.ProgressRing(width=20, height=20, visible=False)
        
        print("创建文件选择器...")
        # 构建文件选择器
        self.folder_picker = ft.FilePicker(on_result=self._on_folder_selected)
        self.page.overlay.append(self.folder_picker)
        
        print("创建对话框...")
        # 创建下载界面
        self.dialog = ft.AlertDialog(
            title=ft.Text("下载麦麦Core (MMC)"),
            content=self._build_dialog_content(),
            actions=[
                ft.TextButton("取消", on_click=self._on_cancel),
            ],
            on_dismiss=self._on_dialog_dismiss,
            modal=True,
        )
        # 将对话框添加到页面的 overlay 中
        self.page.overlay.append(self.dialog)
        print("MMCDownloader 初始化完成")
    
    def _on_source_change(self, e):
        if self.source_dropdown.value == "github":
            self.repo_url = self.repo_url_github
        else:
            self.repo_url = self.repo_url_gitee
        # 重新获取分支
        self.branch_dropdown.disabled = True
        self.branch_dropdown.hint_text = "加载分支列表中..."
        self.page.update()
        threading.Thread(target=self._fetch_branches, daemon=True).start()
    
    def _build_dialog_content(self):
        browse_button = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="浏览...",
            on_click=lambda _: self.folder_picker.get_directory_path(
                dialog_title="选择MMC下载位置"
            )
        )
        # 新的分支和源选择行
        source_branch_row = ft.Row([
            self.source_dropdown,
            self.branch_dropdown,
            self.progress_ring
        ], spacing=10)

        # 新的路径和文件夹名行
        path_row = ft.Row([
            self.project_name_text,
            self.path_text,
            browse_button
        ], spacing=10)

        download_button = ft.ElevatedButton(
            "下载",
            icon=ft.Icons.DOWNLOAD,
            on_click=self._on_download
        )
        github_button = ft.ElevatedButton(
            "访问GitHub仓库手动下载",
            icon=ft.Icons.OPEN_IN_NEW,
            on_click=lambda e: os.startfile(self.repo_url) if os.name == 'nt' else subprocess.run(['xdg-open', self.repo_url])
        )
        return ft.Container(
            content=ft.Column([
                ft.Text("从GitHub或Gitee下载麦麦Core (MMC)的最新代码", size=14),
                source_branch_row,
                path_row,
                ft.Row([download_button], alignment=ft.MainAxisAlignment.START),
                ft.Divider(),
                self.status_text,
                ft.Container(
                    content=self.log_area,
                    padding=5,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=5,
                    bgcolor=ft.Colors.SURFACE_TINT,
                ),
                github_button
            ], spacing=20, width=700),
            padding=10
        )
    
    def _on_folder_selected(self, e):
        if e.path:
            self.path_text.value = e.path
            self.page.update()
    
    def _add_log(self, text, color=None):
        """添加日志到日志区域"""
        self.log_output.append(text)
        if len(self.log_output) > 100:  # 限制日志行数
            self.log_output.pop(0)
        
        # 更新UI
        self.log_area.controls = [
            ft.Text(line, color=color) for line in self.log_output
        ]
        self.page.update()
    
    def _fetch_branches(self):
        """获取仓库的分支列表"""
        try:
            self.status_text.value = "正在获取分支列表..."
            self.progress_ring.visible = True
            self.page.update()

            response = requests.get(f"https://api.github.com/repos/MaiM-with-u/MaiBot/branches")
            if response.status_code == 200:
                branches_data = response.json()
                # 只保留 main 和 dev
                filtered = [(b["name"], "稳定版" if b["name"]=="main" else ("开发版" if b["name"]=="dev" else None)) for b in branches_data]
                filtered = [(k, v) for k, v in filtered if v]
                self.branches = [k for k, v in filtered]
                # 构造下拉选项
                self.branch_dropdown.options = [
                    ft.dropdown.Option(key, text=label) for key, label in filtered
                ]
                self.branch_dropdown.value = "main" if any(k=="main" for k, _ in filtered) else (filtered[0][0] if filtered else None)
                self.branch_dropdown.disabled = False
                self.branch_dropdown.hint_text = ""
                self.status_text.value = f"获取到 {len(self.branches)} 个分支"
                self.log_output.append(f"成功获取到分支列表: {', '.join([v for _, v in filtered])}")
            else:
                error_msg = f"获取分支列表失败: HTTP {response.status_code}"
                self.log_output.append(error_msg)
                self.status_text.value = "获取分支列表失败，请重试"
                self.branch_dropdown.hint_text = "无法获取分支"
        except Exception as ex:
            error_msg = f"获取分支列表时出错: {str(ex)}"
            self.log_output.append(error_msg)
            self.status_text.value = "获取分支列表失败，请重试"
            self.branch_dropdown.hint_text = "无法获取分支"
        finally:
            self.progress_ring.visible = False
            self.log_area.controls = [
                ft.Text(line, color=ft.Colors.ERROR if "失败" in line or "出错" in line else None) 
                for line in self.log_output
            ]
            self.page.update()
    
    def _on_download(self, e):
        """开始下载过程"""
        selected_branch = self.branch_dropdown.value
        self.download_path = self.path_text.value
        
        if not selected_branch:
            self._add_log("请选择一个分支", ft.Colors.ERROR)
            return
        
        if not self.download_path:
            self._add_log("请指定下载路径", ft.Colors.ERROR)
            return
        
        project_name = self.project_name_text.value.strip()
        if not project_name:
            self._add_log("请填写项目文件夹名", ft.Colors.ERROR)
            return

        target_path = os.path.join(self.download_path, project_name)
        if os.path.exists(target_path):
            self._add_log("目标文件夹已存在，请更换名称", ft.Colors.ERROR)
            return

        self.download_path = target_path
        
        # 不再禁用 actions[1]
        self.progress_ring.visible = True
        self.status_text.value = f"正在下载 {selected_branch} 分支..."
        
        # 清空日志
        self.log_area.controls.clear()
        self.log_output = []
        self.log_output.append(f"开始下载 MaiBot ({selected_branch} 分支) 到 {self.download_path}")
        self.log_area.controls = [ft.Text(self.log_output[0])]
        
        self.page.update()
        
        threading.Thread(target=self._download_repo, args=(selected_branch,), daemon=True).start()
    
    def _download_repo(self, branch):
        """在后台线程中执行git clone操作"""
        try:
            # 确保目录存在
            os.makedirs(self.download_path, exist_ok=True)
            
            # 检查目标目录是否为空
            if os.listdir(self.download_path):
                self._add_log(f"警告: 目标目录不为空", ft.Colors.WARNING)
                
                # 检查是否已经是git仓库
                if os.path.exists(os.path.join(self.download_path, ".git")):
                    self._add_log("检测到已存在的Git仓库，将执行pull操作...")
                    
                    # 执行git pull
                    self.process = subprocess.Popen(
                        ["git", "pull", "origin", branch],
                        cwd=self.download_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1
                    )
                else:
                    self._add_log("目标目录不是Git仓库，请选择一个空目录或已存在的仓库", ft.Colors.ERROR)
                    self.status_text.value = "下载失败: 目标目录不为空且不是Git仓库"
                    self.page.update()
                    self._update_ui_after_download(False)
                    return
            else:
                # 如果目录为空，执行git clone
                self._add_log(f"开始克隆仓库，分支: {branch}...")
                
                self.process = subprocess.Popen(
                    ["git", "clone", "-b", branch, self.repo_url, self.download_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
            
            # 处理命令输出
            self._process_output()
                
        except Exception as ex:
            self._add_log(f"下载过程中出错: {str(ex)}", ft.Colors.ERROR)
            self.status_text.value = f"下载失败: {str(ex)}"
            self.page.update()
            self._update_ui_after_download(False)
    
    def _process_output(self):
        """处理命令的输出流"""
        if not self.process:
            return

        output_lines = []

        for line in self.process.stdout:
            output_lines.append(line.strip())
            self._add_log(line.strip())

        exit_code = self.process.wait()

        if exit_code == 0:
            self._add_log("下载完成！", ft.Colors.SUCCESS)
            self.status_text.value = "下载成功！"
            self.page.update()
            self._update_ui_after_download(True)
        else:
            # 优先查找 fatal 或 error
            fatal_line = next((l for l in output_lines if "fatal:" in l.lower()), None)
            error_line = next((l for l in output_lines if "error:" in l.lower()), None)
            last_error = fatal_line or error_line or (output_lines[-1] if output_lines else "未知错误")
            self._add_log(f"下载失败，错误代码: {exit_code}", ft.Colors.ERROR)
            self.status_text.value = f"下载失败: {last_error}"
            self.page.update()
            self._update_ui_after_download(False)
            
            if exit_code != 0 and os.path.exists(self.download_path):
                try:
                    shutil.rmtree(self.download_path)
                    self._add_log("下载失败，已自动删除创建的文件夹", ft.Colors.WARNING)
                except Exception as ex:
                    self._add_log(f"删除失败: {str(ex)}", ft.Colors.ERROR)
    
    def _update_ui_after_download(self, success):
        """更新下载完成后的UI状态"""
        # 恢复按钮状态
        self.progress_ring.visible = False
        
        # 更新状态
        if success:
            self.dialog.actions = [
                ft.TextButton("关闭", on_click=self._on_cancel),
                ft.ElevatedButton("打开文件夹", icon=ft.Icons.FOLDER_OPEN, on_click=self._open_folder),
            ]
        
        # 更新UI
        self.page.update()
    
    def _open_folder(self, e):
        """打开下载文件夹"""
        try:
            # 根据操作系统选择打开文件夹的命令
            if os.name == 'nt':  # Windows
                os.startfile(self.download_path)
            elif os.name == 'posix':  # macOS 和 Linux
                subprocess.run(['xdg-open', self.download_path])
                
            self._on_cancel(e)
        except Exception as ex:
            self._add_log(f"打开文件夹失败: {str(ex)}", ft.Colors.ERROR)
    
    def _on_cancel(self, e=None):
        """取消下载并关闭对话框"""
        # 如果有正在运行的进程，尝试终止它
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self._add_log("已取消下载操作", ft.Colors.WARNING)
            except:
                pass
                
        # 关闭对话框
        self.dialog.open = False
        self.page.update()
        
        # 清理资源
        if self.folder_picker in self.page.overlay:
            self.page.overlay.remove(self.folder_picker)
            
        # 调用关闭回调
        if self.on_close_callback:
            self.on_close_callback()
    
    def _on_dialog_dismiss(self, e):
        """对话框被关闭时的回调"""
        self._on_cancel(e)
    
    def show(self):
        """显示下载对话框"""
        print("准备显示对话框...")
        self.dialog.open = True
        self.page.update()
        print("对话框显示设置完成")
        
        # 启动后台线程获取分支列表
        threading.Thread(target=self._fetch_branches, daemon=True).start()


def show_mmc_downloader(page: ft.Page, on_close_callback=None):
    """显示MMC下载器对话框"""
    print("开始创建下载器...")
    downloader = MMCDownloader(page, on_close_callback)
    print("下载器创建完成，准备显示...")
    downloader.show()
    print("下载器显示完成")
    return downloader


# 测试代码 - 当直接运行此文件时执行
if __name__ == "__main__":
    def main(page: ft.Page):
        print("初始化主窗口...")
        page.title = "MMC下载器测试"
        page.window.width = 1000
        page.window.height = 800
        page.theme_mode = ft.ThemeMode.LIGHT
        
        def on_click(e):
            print("按钮被点击")
            show_mmc_downloader(page)
            print("show_mmc_downloader 调用完成")
            
        page.add(
            ft.ElevatedButton("打开MMC下载器", on_click=on_click)
        )
        print("主窗口初始化完成")
    
    print("启动应用...")
    ft.app(target=main) 