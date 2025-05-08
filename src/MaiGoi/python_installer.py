import flet as ft
import os
import sys
import subprocess
import platform
from pathlib import Path
import threading
import urllib.request
import time

class PythonInstallerApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Python 环境安装助手"
        self.page.window.width = 800
        self.page.window.height = 900
        self.page.padding = 20
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        
        # 状态控件
        self.status_text = ft.Text("正在检测系统环境...", size=14)
        self.progress_bar = ft.ProgressBar(visible=False, width=600)
        self.log_view = ft.ListView(
            expand=1,
            spacing=10,
            padding=10,
            auto_scroll=True,
            height=200,
        )
        
        # 操作按钮
        self.download_button = ft.ElevatedButton(
            "下载 Python 3.12.8",
            icon=ft.icons.DOWNLOAD,
            on_click=self.download_python,
            disabled=True,
            visible=False
        )
        
        self.install_button = ft.ElevatedButton(
            "运行安装程序",
            icon=ft.icons.INSTALL_DESKTOP,
            on_click=self.run_installer,
            disabled=True,
            visible=False
        )
        
        self.create_venv_button = ft.ElevatedButton(
            "创建虚拟环境",
            icon=ft.icons.CREATE_NEW_FOLDER,
            on_click=self.create_venv,
            disabled=True,
            visible=False
        )
        
        # 添加安装依赖按钮
        self.install_req_button = ft.ElevatedButton(
            "安装依赖文件",
            icon=ft.icons.LIBRARY_BOOKS,
            on_click=self.pick_requirements_file,
            disabled=True,
            visible=False
        )
        
        self.refresh_button = ft.IconButton(
            icon=ft.icons.REFRESH,
            tooltip="刷新检测",
            on_click=self.check_python_env
        )
        
        # 文件选择器
        self.file_picker = ft.FilePicker(on_result=self.on_requirements_picked)
        page.overlay.append(self.file_picker)
        
        # 构建UI
        self.build_ui()
        
        # 立即执行检测，不等待window_on_loaded事件
        threading.Thread(target=self.check_python_env).start()
    
    def build_ui(self):
        """构建用户界面"""
        self.page.controls.clear()
        
        header = ft.Column([
            ft.Row([
                ft.Text("Python 环境安装助手", size=24, weight=ft.FontWeight.BOLD),
                self.refresh_button,
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Text("本工具将帮助您检测并安装麦麦Bot所需的Python环境", size=16),
            ft.Divider(),
        ])
        
        status_section = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.icons.INFO_OUTLINE, color=ft.colors.BLUE),
                        self.status_text,
                    ]),
                    self.progress_bar,
                ], tight=True),
                padding=15
            ),
            margin=ft.margin.only(bottom=10)
        )
        
        buttons_row = ft.Row(
            [self.download_button, self.install_button, self.create_venv_button, self.install_req_button],
            wrap=True,
            spacing=10
        )
        
        log_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Text("操作日志:", weight=ft.FontWeight.BOLD),
                    ft.Container(
                        content=self.log_view,
                        border=ft.border.all(1, ft.colors.OUTLINE),
                        border_radius=5,
                        padding=5,
                        height=400,
                    ),
                ]),
                padding=15,
            ),
        )
        
        # 添加所有元素到页面
        self.page.add(
            header,
            status_section,
            buttons_row,
            log_card,
        )
        self.page.update()
    
    def add_log(self, message, color="black"):
        """向日志区域添加消息"""
        self.log_view.controls.append(ft.Text(message, color=color, selectable=True))
        self.log_view.update()
    
    def check_python_env(self, e=None):
        """检查系统中的Python环境"""
        def run_check():
            # 更新状态
            self.update_status("正在检测系统Python环境...", show_progress=True)
            self.add_log("开始检测系统Python环境...")
            
            # 复位按钮状态
            self.download_button.visible = False
            self.install_button.visible = False
            self.create_venv_button.visible = False
            self.install_req_button.visible = False
            self.page.update()
            
            # 检测系统类型
            system_info = f"操作系统: {platform.system()} {platform.release()}, {platform.architecture()[0]}"
            self.add_log(system_info)
            
            # 查找Python路径
            python_paths = self.find_python_paths()
            
            if not python_paths:
                self.add_log("未检测到系统中的Python安装。", color="orange")
                self.update_status("未找到Python安装，请点击下载按钮", show_progress=False)
                self.download_button.disabled = False
                self.download_button.visible = True
                self.page.update()
                return
            
            # 检查是否有Python 3.12.x版本
            python312_path = None
            for path in python_paths:
                version = self.get_python_version(path)
                if version:
                    self.add_log(f"检测到Python: {path} - 版本: {version}")
                    if version.startswith("3.12"):
                        python312_path = path
                        self.add_log(f"✅ 找到Python 3.12.x版本: {path}", color="green")
            
            if not python312_path:
                self.add_log("未检测到Python 3.12.x版本，推荐下载安装。", color="orange")
                self.update_status("需要Python 3.12.x版本", show_progress=False)
                self.download_button.disabled = False
                self.download_button.visible = True
                self.page.update()
                return
            
            # 检查虚拟环境
            self.add_log("检测项目虚拟环境...")
            venv_path = Path("venv")
            venv_python = None
            
            if platform.system() == "Windows":
                venv_python_path = venv_path / "Scripts" / "python.exe"
            else:
                venv_python_path = venv_path / "bin" / "python"
                
            if venv_path.exists() and venv_python_path.exists():
                self.add_log("✅ 检测到有效的虚拟环境", color="green")
                self.update_status("Python 3.12.x和虚拟环境已就绪", show_progress=False)
                # 启用安装依赖按钮
                self.install_req_button.disabled = False
                self.install_req_button.visible = True
            else:
                self.add_log("未检测到有效的虚拟环境，需要创建。", color="orange")
                self.update_status("需要创建虚拟环境", show_progress=False)
                self.create_venv_button.disabled = False
                self.create_venv_button.visible = True
            
            self.page.update()
        
        # 在后台线程运行检查逻辑
        threading.Thread(target=run_check).start()
    
    def find_python_paths(self):
        """查找系统中的Python路径"""
        paths = []
        try:
            if platform.system() == "Windows":
                # Windows下查找Python路径
                output = subprocess.check_output(["where", "python"], text=True, stderr=subprocess.PIPE)
                paths = [line.strip() for line in output.splitlines() if line.strip()]
            else:
                # Linux/Mac下查找Python路径
                output = subprocess.check_output(["which", "python3"], text=True, stderr=subprocess.PIPE)
                paths.append(output.strip())
        except subprocess.CalledProcessError:
            # 命令执行失败，可能是未安装Python
            pass
        
        # 针对Windows，可能还需要检查Python Launcher路径
        if platform.system() == "Windows":
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
            python_dirs = list(Path(program_files).glob("Python*"))
            for py_dir in python_dirs:
                python_exe = py_dir / "python.exe"
                if python_exe.exists() and str(python_exe) not in paths:
                    paths.append(str(python_exe))
        
        return paths
    
    def get_python_version(self, python_path):
        """获取指定Python路径的版本"""
        try:
            output = subprocess.check_output([python_path, "-V"], text=True, stderr=subprocess.STDOUT)
            return output.strip().split()[1]  # 通常返回类似 "Python 3.9.0" 的结果
        except:
            return None
    
    def update_status(self, message, show_progress=True):
        """更新状态区域"""
        self.status_text.value = message
        self.progress_bar.visible = show_progress
        self.status_text.update()
        self.progress_bar.update()
    
    def download_python(self, e):
        """下载Python安装包"""
        def do_download():
            self.download_button.disabled = True
            self.update_status("正在下载Python 3.12.8安装包...", show_progress=True)
            self.page.update()
            
            # 确定系统架构
            is_64bit = platform.architecture()[0] == "64bit"
            arch_suffix = "amd64" if is_64bit else ""
            
            # 下载URL
            url = f"https://mirrors.aliyun.com/python-release/windows/python-3.12.8-{arch_suffix}.exe"
            self.add_log(f"开始从{url}下载安装包...")
            
            # 下载文件
            installer_path = "python-3.12.8-installer.exe"
            try:
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener)
                
                def reporthook(blocknum, blocksize, totalsize):
                    readsofar = blocknum * blocksize
                    if totalsize > 0:
                        percent = readsofar * 100 / totalsize
                        self.progress_bar.value = percent / 100
                        self.progress_bar.update()
                    
                urllib.request.urlretrieve(url, installer_path, reporthook)
                
                self.add_log(f"✅ 下载完成: {installer_path}", color="green")
                self.update_status("Python安装包下载完成，请点击安装按钮", show_progress=False)
                self.install_button.disabled = False
                self.install_button.visible = True
            except Exception as e:
                self.add_log(f"❌ 下载失败: {str(e)}", color="red")
                self.update_status("下载失败，请检查网络连接", show_progress=False)
                self.download_button.disabled = False
            
            self.page.update()
        
        # 在后台线程运行下载
        threading.Thread(target=do_download).start()
    
    def run_installer(self, e):
        """运行Python安装程序"""
        installer_path = "python-3.12.8-installer.exe"
        if not os.path.exists(installer_path):
            self.add_log("❌ 安装程序不存在，请重新下载", color="red")
            return
        
        self.add_log("正在启动Python安装程序...")
        self.add_log("提示: 安装时请勾选 'Add Python 3.12 to PATH' 选项", color="blue")
        
        try:
            if platform.system() == "Windows":
                os.startfile(installer_path)
                self.add_log("安装程序已启动，请按照向导完成安装")
                self.add_log("安装完成后，请点击刷新按钮重新检测环境", color="orange")
            else:
                self.add_log("❌ 非Windows系统无法直接运行安装程序", color="red")
        except Exception as e:
            self.add_log(f"❌ 启动安装程序失败: {str(e)}", color="red")
    
    def create_venv(self, e):
        """创建Python虚拟环境"""
        def do_create_venv():
            self.create_venv_button.disabled = True
            self.update_status("正在创建虚拟环境...", show_progress=True)
            self.page.update()
            
            self.add_log("开始创建虚拟环境...")
            
            # 先查找合适的Python 3.12.x
            python_paths = self.find_python_paths()
            python312_path = None
            
            for path in python_paths:
                version = self.get_python_version(path)
                if version and version.startswith("3.12"):
                    python312_path = path
                    break
            
            if not python312_path:
                self.add_log("❌ 未找到Python 3.12.x，无法创建虚拟环境", color="red")
                self.update_status("创建虚拟环境失败", show_progress=False)
                self.create_venv_button.disabled = False
                self.page.update()
                return
            
            # 如果已有venv目录，先删除
            venv_path = Path("venv")
            if venv_path.exists():
                self.add_log("移除现有的虚拟环境...")
                try:
                    import shutil
                    shutil.rmtree("venv")
                except Exception as e:
                    self.add_log(f"❌ 移除现有虚拟环境失败: {str(e)}", color="red")
                    self.update_status("创建虚拟环境失败", show_progress=False)
                    self.create_venv_button.disabled = False
                    self.page.update()
                    return
            
            # 创建虚拟环境
            try:
                self.add_log(f"使用 {python312_path} 创建虚拟环境...")
                
                # 运行venv模块创建虚拟环境
                process = subprocess.Popen(
                    [python312_path, "-m", "venv", "venv"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                stdout, stderr = process.communicate()
                
                if process.returncode == 0:
                    self.add_log("✅ 虚拟环境创建成功", color="green")
                    self.update_status("虚拟环境已创建，现在可以安装依赖", show_progress=False)
                    
                    # 启用安装依赖按钮
                    self.install_req_button.disabled = False
                    self.install_req_button.visible = True
                    
                    # 显示成功消息
                    self.page.dialog = ft.AlertDialog(
                        title=ft.Text("虚拟环境已创建"),
                        content=ft.Text("Python 环境已准备就绪！现在您可以选择安装依赖。"),
                        actions=[
                            ft.TextButton("关闭", on_click=lambda _: self.close_dialog()),
                            ft.ElevatedButton("安装依赖", on_click=lambda _: self.close_dialog_and_pick_req()),
                        ],
                        actions_alignment=ft.MainAxisAlignment.END,
                    )
                    self.page.dialog.open = True
                    self.page.update()
                else:
                    error_msg = stderr or "未知错误"
                    self.add_log(f"❌ 创建虚拟环境失败: {error_msg}", color="red")
                    self.update_status("创建虚拟环境失败", show_progress=False)
                    self.create_venv_button.disabled = False
            except Exception as e:
                self.add_log(f"❌ 创建虚拟环境时发生异常: {str(e)}", color="red")
                self.update_status("创建虚拟环境失败", show_progress=False)
                self.create_venv_button.disabled = False
            
            self.page.update()
        
        # 在后台线程运行
        threading.Thread(target=do_create_venv).start()
    
    def close_dialog(self):
        """关闭对话框"""
        self.page.dialog.open = False
        self.page.update()
    
    def close_dialog_and_pick_req(self):
        """关闭对话框并选择requirements文件"""
        self.page.dialog.open = False
        self.page.update()
        self.pick_requirements_file()
    
    def pick_requirements_file(self, e=None):
        """打开文件选择器，选择requirements.txt文件"""
        self.file_picker.pick_files(
            dialog_title="选择依赖文件 (requirements.txt)",
            allowed_extensions=["txt"],
            allow_multiple=False
        )
    
    def on_requirements_picked(self, e):
        """处理选择的requirements文件"""
        if not e.files or len(e.files) == 0:
            return
            
        req_file_path = e.files[0].path
        if not req_file_path or not os.path.exists(req_file_path):
            self.add_log("❌ 未选择有效的依赖文件", color="red")
            return
            
        # 开始安装依赖
        threading.Thread(target=lambda: self.install_requirements(req_file_path)).start()
    
    def install_requirements(self, req_file_path):
        """安装requirements.txt中的依赖"""
        self.install_req_button.disabled = True
        self.install_req_button.update()
        
        self.update_status(f"正在安装依赖: {os.path.basename(req_file_path)}...", show_progress=True)
        self.add_log(f"开始安装依赖: {req_file_path}")
        
        dialog_content = ft.Column([
            ft.Text("请选择安装依赖时使用的pip下载源:"),
            ft.RadioGroup(
                value="1", # 默认选择第一个
                content=ft.Column([
                    ft.Radio(value="1", label="阿里云 (https://mirrors.aliyun.com/pypi/simple) [推荐]"),
                    ft.Radio(value="2", label="清华 (https://pypi.tuna.tsinghua.edu.cn/simple)"),
                    ft.Radio(value="3", label="豆瓣 (https://pypi.douban.com/simple)"),
                    ft.Radio(value="4", label="官方 (https://pypi.org/simple)"),
                ]),
            ),
        ], tight=True, spacing=10)

        # 创建 AlertDialog 实例，但不立即赋值给 self.page.dialog 或打开
        current_dialog = ft.AlertDialog(
            title=ft.Text("选择pip下载源"),
            content=dialog_content,
            actions=[
                ft.TextButton("取消", on_click=lambda _: self.cancel_install_req(current_dialog)),
                ft.ElevatedButton("开始安装", on_click=lambda e_args: self.start_install_req(e_args, req_file_path, current_dialog)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
            modal=True # 通常这类对话框是模态的
        )
        self.page.dialog = current_dialog # 赋值给 page.dialog 以便后续引用
        self.page.open(current_dialog) # 使用 page.open() 来显示对话框
        self.page.update() # 确保 page.open 生效
    
    def cancel_install_req(self, dialog_to_close=None):
        """取消安装依赖"""
        if dialog_to_close:
            dialog_to_close.open = False
        elif self.page.dialog: # Fallback if not passed directly
            self.page.dialog.open = False
            
        self.update_status("安装依赖已取消", show_progress=False)
        self.install_req_button.disabled = False
        self.install_req_button.update()
        self.page.update() # 更新页面以关闭对话框等
    
    def start_install_req(self, e, req_file_path, dialog_to_close=None):
        """开始安装依赖（在选择pip源后）"""
        source_choice = "4" # 默认官方源
        # 从传递的对话框实例中获取 RadioGroup 的值
        if dialog_to_close and isinstance(dialog_to_close.content, ft.Column) and \
           len(dialog_to_close.content.controls) > 1 and isinstance(dialog_to_close.content.controls[1], ft.RadioGroup):
            source_choice = dialog_to_close.content.controls[1].value
        elif self.page.dialog and isinstance(self.page.dialog.content, ft.Column) and \
             len(self.page.dialog.content.controls) > 1 and isinstance(self.page.dialog.content.controls[1], ft.RadioGroup):
            # Fallback if dialog_to_close wasn't correctly passed or is not the one with RadioGroup
            source_choice = self.page.dialog.content.controls[1].value
        else:
            self.add_log("无法获取pip源选择，将使用默认官方源", color="orange")

        pip_index_url = {
            "1": "https://mirrors.aliyun.com/pypi/simple",
            "2": "https://pypi.tuna.tsinghua.edu.cn/simple",
            "3": "https://pypi.douban.com/simple",
        }.get(source_choice, "https://pypi.org/simple")
        
        # 关闭对话框
        if dialog_to_close:
            dialog_to_close.open = False
        elif self.page.dialog: # Fallback
            self.page.dialog.open = False
        self.page.update()
        
        threading.Thread(target=lambda: self.do_install_requirements(req_file_path, pip_index_url)).start()
    
    def do_install_requirements(self, req_file_path, pip_index_url):
        """执行依赖安装"""
        self.add_log(f"使用pip源: {pip_index_url}")
        
        # 获取python路径
        if platform.system() == "Windows":
            venv_python = os.path.abspath("venv/Scripts/python.exe")
            venv_pip = os.path.abspath("venv/Scripts/pip.exe")
        else:
            venv_python = os.path.abspath("venv/bin/python")
            venv_pip = os.path.abspath("venv/bin/pip")
        
        # 更新pip
        self.add_log("正在更新pip...")
        try:
            upgrade_cmd = [
                venv_python, "-m", "pip", "install", 
                "-i", pip_index_url, 
                "--upgrade", "pip"
            ]
            
            process = subprocess.Popen(
                upgrade_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                self.add_log("✅ pip更新成功", color="green")
            else:
                self.add_log(f"⚠️ pip更新可能未成功完成: {stderr}", color="orange")
        except Exception as e:
            self.add_log(f"⚠️ pip更新过程中出现错误: {str(e)}", color="orange")
        
        # 安装依赖
        self.add_log(f"开始安装依赖: {req_file_path}...")
        self.update_status("正在安装依赖，这可能需要几分钟...", show_progress=True)
        
        try:
            install_cmd = [
                venv_pip, "install", 
                "-i", pip_index_url, 
                "-r", req_file_path
            ]
            
            process = subprocess.Popen(
                install_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # 行缓冲
                universal_newlines=True
            )
            
            # 实时读取输出
            for line in process.stdout:
                line = line.strip()
                if line:
                    if "ERROR" in line:
                        self.add_log(line, color="red")
                    elif "WARNING" in line:
                        self.add_log(line, color="orange")
                    elif "Successfully installed" in line:
                        self.add_log(line, color="green")
                    else:
                        # 过滤掉一些不太重要的输出
                        if not line.startswith("Requirement already satisfied"):
                            self.add_log(line)
            
            # 确保进程完成
            returncode = process.wait()
            
            # 读取stderr
            stderr = process.stderr.read()
            
            if returncode == 0:
                self.add_log("✅ 依赖安装成功！", color="green")
                self.update_status("Python环境和依赖已全部准备就绪", show_progress=False)
                
                # 显示成功消息
                self.page.dialog = ft.AlertDialog(
                    title=ft.Text("安装完成"),
                    content=ft.Text("所有依赖已成功安装！\n现在您可以关闭此窗口，继续使用MaiBot启动器。"),
                    actions=[
                        ft.TextButton("关闭", on_click=lambda _: self.close_dialog()),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                self.page.dialog.open = True
            else:
                self.add_log(f"❌ 依赖安装失败: {stderr}", color="red")
                self.update_status("安装依赖失败", show_progress=False)
        except Exception as e:
            self.add_log(f"❌ 安装过程中发生异常: {str(e)}", color="red")
            self.update_status("安装依赖失败", show_progress=False)
        
        # 启用按钮
        self.install_req_button.disabled = False
        self.page.update()

def main(page: ft.Page):
    PythonInstallerApp(page)

# 直接运行此脚本时启动应用
if __name__ == "__main__":
    ft.app(target=main) 