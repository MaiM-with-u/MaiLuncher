import flet as ft
import asyncio
import os
import json
import time
import traceback
import random
import httpx
from datetime import datetime


API_HOST = "localhost"  # API主机名
API_PORT = 8000  # API端口，默认值
API_BASE_URL = f"http://{API_HOST}:{API_PORT}/api/v1"  # API基础URL

# 如果设置了环境变量，则使用环境变量中的配置
if "MAIBOT_API_PORT" in os.environ:
    try:
        API_PORT = int(os.environ["MAIBOT_API_PORT"])
        API_BASE_URL = f"http://{API_HOST}:{API_PORT}/api/v1"
        print(f"[配置] 使用环境变量中的API端口: {API_PORT}")
    except ValueError:
        print(f"[配置] 环境变量MAIBOT_API_PORT值无效: {os.environ['MAIBOT_API_PORT']}")

print(f"[配置] 使用API地址: {API_BASE_URL}")

REFRESH_INTERVAL_SECONDS = 5  # 刷新间隔（秒）
MAX_HISTORY_POINTS = 1000  # 图表数据点 (Tkinter version uses 1000)
MAX_STREAMS_TO_DISPLAY = 15  # 最多显示的流数量 (Tkinter version uses 15)
MAX_QUEUE_SIZE = 30  # 历史想法队列最大长度 (Tkinter version uses 30)
CHART_DISPLAY_TIMESPAN_SECONDS = 10 * 60  # 图表显示最近10分钟的数据
LOG_TRUNCATE_INTERVAL_SECONDS = 10 * 60  # 每10分钟清理一次日志
LOG_TRUNCATE_THRESHOLD_LINES = 600     # 当日志超过这么多行时触发清理
LOG_TRUNCATE_RETAIN_LINES = 500        # 清理后，保留这么多行
CHART_HEIGHT = 250  # 图表区域高度
DEFAULT_AUTO_SCROLL = True  # 默认开启自动滚动

# --- 子流聊天状态枚举 --- #
# 与心流模块中定义保持一致
CHAT_STATES = [
    {"key": "ABSENT", "text": "没在看群"},
    {"key": "CHAT", "text": "随便水群"},
    {"key": "FOCUSED", "text": "认真水群"},
]

# --- 重要: API使用的实际枚举值，确保与ChatState一致 --- #
# API需要的是中文描述值，而不是英文枚举键
API_CHAT_STATE_VALUES = {"ABSENT": "没在看群", "CHAT": "随便水群", "FOCUSED": "认真水群"}


# --- 辅助函数 ---
def format_timestamp(ts):
    """辅助函数：格式化时间戳，处理 None 或无效值"""
    if ts is None:
        return "无"
    try:
        # 假设 ts 是 float 类型的时间戳
        dt_object = datetime.fromtimestamp(float(ts))
        return dt_object.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return "Invalid Time"


def get_random_flet_color():
    """生成一个随机的 Flet 颜色字符串。"""
    r = random.randint(50, 200)
    g = random.randint(50, 200)
    b = random.randint(50, 200)
    return f"#{r:02x}{g:02x}{b:02x}"





class InterestMonitorDisplay(ft.Column):
    """一个 Flet 控件，用于显示兴趣监控图表和信息。"""

    def __init__(self):
        super().__init__(
            expand=True,
        )
        # --- 状态变量 ---
        self.LOG_FILE_PATH = ""
        
        
        self.log_reader_task = None
        self.log_truncate_task = None # 新增：日志清理任务
        self.stream_history = {}  # {stream_id: deque([(ts, interest), ...])}
        self.probability_history = {}  # {stream_id: deque([(ts, probability), ...])}
        self.stream_display_names = {}  # {stream_id: display_name}
        self.stream_colors = {}  # {stream_id: color_string}
        self.selected_stream_id_for_details = None
        self.last_log_read_time = 0  # 上次读取日志的时间戳
        self.is_expanded = True  # 新增：跟踪是否展开显示
        self.stream_details = {}  # 存储子流详情
        # 新增：监控器切换显示回调函数
        self.on_toggle = None  # 外部可以设置此回调函数

        # --- 新增：存储其他参数 ---
        # 顶层信息 (直接使用 Text 控件引用)
        self.global_mai_state_text = ft.Text("状态: N/A | 活跃聊天数: 0", size=10, width=300)
        # 子流最新状态 (key: stream_id)
        self.stream_sub_minds = {}
        self.stream_chat_states = {}
        self.stream_threshold_status = {}
        self.stream_last_active = {}

        # --- UI 控件引用 ---
        self.status_text = ft.Text("正在初始化监控器...", size=10, color=ft.colors.SECONDARY)

        # --- 全局信息 Row ---
        self.global_info_row = ft.Row(
            controls=[
                self.global_mai_state_text,
            ],
            spacing=15,
            wrap=False,  # 防止换行
        )

        # --- 图表控件 ---
        self.main_chart = ft.LineChart(height=CHART_HEIGHT, expand=True)
        # --- 新增：图例 Column ---
        self.legend_column = ft.Column(
            controls=[],
            width=150,  # 给图例固定宽度
            scroll=ft.ScrollMode.ADAPTIVE,  # 如果图例过多则滚动
            spacing=2,
        )

        self.stream_dropdown = ft.Dropdown(
            label="选择流查看详情",
            options=[],
            width=200,  # 调整宽度以适应并排布局
            on_change=self.on_stream_selected,
        )

        # 创建合并的详情图表
        self.detail_chart_combined = ft.LineChart(height=CHART_HEIGHT)

        # --- 创建状态控制下拉菜单 ---
        self.state_dropdown = ft.Dropdown(
            label="选择目标状态",
            options=[ft.dropdown.Option(text=state["text"], key=state["key"]) for state in CHAT_STATES],
            width=150,  # 调整宽度以适应并排布局
        )

        # --- 创建控制按钮 ---
        self.control_button = ft.ElevatedButton(
            "设置状态",
            icon=ft.icons.SWAP_HORIZ,
            on_click=self.handle_control_button_click,
            disabled=True,  # 初始禁用
        )

        # --- 控制按钮行 ---
        self.control_row = ft.Row(
            [
                self.state_dropdown,
                self.control_button,
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=10,
        )

        # --- 单个流详情文本控件 (Column) ---
        self.detail_texts = ft.Column(
            [
                # --- 合并所有详情为一行 ---
                ft.Text(
                    "状态: 无 | 最后活跃: 无",
                    size=20,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    tooltip="查看详细状态信息",
                ),
            ],
            spacing=2,
        )

        # --- 新增：切换显示按钮 ---
        self.toggle_button = ft.IconButton(
            icon=ft.icons.ARROW_UPWARD, tooltip="隐藏兴趣监控", on_click=self.toggle_display
        )

        # --- 新增：顶部栏包含状态和切换按钮 ---
        self.top_bar = ft.Row(
            [
                self.status_text,
                # ft.Spacer(), # Flet没有Spacer组件
                ft.Container(expand=True),  # 使用可扩展容器代替Spacer
                self.toggle_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # --- 构建整体布局 ---
        # 创建 Tabs 控件
        self.tabs_control = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="所有流兴趣度",
                    content=ft.Column(
                        controls=[
                            self.global_info_row,  # 将全局信息行移动到这里
                            ft.Row(
                                controls=[
                                    self.main_chart,  # 图表在左侧
                                    self.legend_column,  # 图例在右侧
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.START,
                                expand=True,  # 让 Row 扩展
                            ),
                        ],
                    ),
                ),
                ft.Tab(
                    text="单个流详情",
                    content=ft.Column(
                        [
                            # 添加顶部间距，防止被标签遮挡
                            ft.Container(height=10),
                            # --- 修改：流选择、状态设置和详情文本放在同一行 ---
                            ft.Row(
                                [
                                    self.stream_dropdown,  # 流选择下拉菜单
                                    ft.Container(width=10),  # 添加间距
                                    self.control_row,  # 状态控制行
                                    ft.Container(width=15),  # 添加间距
                                    self.detail_texts,  # 显示文本信息的 Column (现在移到这一行)
                                ],
                                alignment=ft.MainAxisAlignment.START,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Divider(height=10, color=ft.colors.TRANSPARENT),
                            # 合并的图表显示
                            ft.Column(
                                [ft.Text("兴趣度和HFC概率", weight=ft.FontWeight.BOLD), self.detail_chart_combined],
                                expand=1,
                            ),
                        ],
                        scroll=ft.ScrollMode.ADAPTIVE,  # 自适应滚动
                    ),
                ),
            ],
            expand=True,  # 让 Tabs 在父 Column 中扩展
        )

        # 主要内容区域（可隐藏部分）
        self.content_area = ft.Column(
            [
                self.tabs_control,  # 标签页
            ],
            expand=True,
        )

        self.controls = [
            self.top_bar,  # 顶部栏包含状态和切换按钮
            self.content_area,  # 可隐藏的内容区域
        ]

        print("[InterestMonitor] 初始化完成")
        
    def set_log_path(self, log_path):
        self.LOG_FILE_PATH = os.path.join(log_path, "logs", "interest", "interest_history.log")

    # --- 新增: 状态切换处理函数 ---
    async def change_stream_state(self, e):
        """处理状态切换按钮点击"""
        if not self.selected_stream_id_for_details or not self.state_dropdown.value:
            # 显示错误提示
            if self.page:
                self.page.snack_bar = ft.SnackBar(content=ft.Text("请先选择子流和目标状态"), show_close_icon=True)
                self.page.snack_bar.open = True
                self.page.update()
            return

        subflow_id = self.selected_stream_id_for_details
        target_state = self.state_dropdown.value  # 这是英文的枚举值如 "ABSENT"

        # 获取对应的中文显示文本，用于通知
        state_text = next((state["text"] for state in CHAT_STATES if state["key"] == target_state), target_state)

        try:
            # 使用API切换子心流状态
            success, error_msg = await self.change_subheartflow_status(subflow_id, target_state)

            if success:
                # 命令发送成功
                if self.page:
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"已成功将子流 {subflow_id} 设置为 {state_text}"),
                        show_close_icon=True,
                        bgcolor=ft.colors.GREEN_200,
                    )
                    self.page.snack_bar.open = True
                    self.page.update()
            else:
                # 命令发送失败
                if self.page:
                    self.page.snack_bar = ft.SnackBar(
                        content=ft.Text(f"命令发送失败: {error_msg}"), show_close_icon=True, bgcolor=ft.colors.RED_200
                    )
                    self.page.snack_bar.open = True
                    self.page.update()

        except Exception as ex:
            print(f"[调试] 切换子心流状态时出错: {ex}")
            traceback.print_exc()
            if self.page:
                self.page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"命令发送失败，请查看日志: {str(ex)}"),
                    show_close_icon=True,
                    bgcolor=ft.colors.RED_200,
                )
                self.page.snack_bar.open = True
                self.page.update()

    async def change_subheartflow_status(self, subflow_id, target_state):
        """通过API改变子心流状态"""
        try:
            # 验证参数
            if not subflow_id:
                print("[调试] 错误: subflow_id为空")
                return False, "子流ID不能为空"

            # 验证状态值是否为有效的枚举
            valid_states = [state["key"] for state in CHAT_STATES]
            if target_state not in valid_states:
                print(f"[调试] 错误: 无效的目标状态 {target_state}，有效值: {valid_states}")
                return False, f"无效的目标状态: {target_state}"

            # 转换状态到API期望的格式
            api_state_value = API_CHAT_STATE_VALUES.get(target_state, target_state)
            print(f"[调试] 转换状态值: {target_state} -> {api_state_value}")

            url = f"{API_BASE_URL}/gui/subheartflow/forced_change_status"

            # API需要的是查询参数，使用转换后的状态值
            params = {"subheartflow_id": subflow_id, "status": api_state_value}

            print(f"[调试] 准备发送API请求: URL={url}")
            print(f"[调试] URL参数={params}")

            async with httpx.AsyncClient(timeout=30.0) as client:  # 增加超时时间到30秒
                print("[调试] 正在发送API请求...")
                try:
                    response = await client.post(url, params=params)

                    print(f"[调试] 收到API响应: 状态码={response.status_code}")
                    print(f"[调试] 响应内容: {response.text}")
                except httpx.TimeoutException:
                    print(f"[调试] API请求超时，服务器可能未运行或端口配置错误: {url}")
                    return False, "API请求超时"

            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"[调试] 解析响应JSON: {result}")
                    if result.get("status") == "success":
                        print(f"[InterestMonitor] API请求成功: 将子流 {subflow_id} 设置为 {target_state}")
                        return True, None
                    else:
                        error_msg = result.get("reason", "未知错误")
                        print(f"[InterestMonitor] API请求失败: {error_msg}")
                        return False, error_msg
                except json.JSONDecodeError:
                    print(f"[调试] 响应不是有效的JSON: {response.text}")
                    return False, "服务器响应不是有效的JSON"
            else:
                print(f"[InterestMonitor] API请求失败: HTTP状态码 {response.status_code}")
                return False, f"HTTP错误: {response.status_code}"

        except Exception as e:
            print(f"[InterestMonitor] 调用API出错: {e}")
            traceback.print_exc()
            return False, str(e)

    def handle_control_button_click(self, e):
        """处理控制按钮点击，启动异步任务"""
        try:
            print("[调试] 控制按钮被点击")
            if self.page:
                print("[调试] 准备启动异步任务")

                # 创建一个不需要参数的异步包装函数
                async def async_wrapper():
                    return await self.change_stream_state(e)

                # 使用包装函数作为任务
                async_task = self.page.run_task(async_wrapper)
                print(f"[调试] 异步任务已启动: {async_task}")
            else:
                print("[调试] 错误: self.page 为 None")
        except Exception as ex:
            print(f"[调试] 启动任务时出错: {ex}")
            traceback.print_exc()

    def toggle_display(self, e):
        """切换兴趣监控的显示/隐藏状态"""
        self.is_expanded = not self.is_expanded

        # 更新按钮图标和提示
        if self.is_expanded:
            self.toggle_button.icon = ft.icons.ARROW_DOWNWARD
            self.toggle_button.tooltip = "隐藏兴趣监控"
        else:
            self.toggle_button.icon = ft.icons.ARROW_UPWARD
            self.toggle_button.tooltip = "显示兴趣监控"

        # 切换内容区域的可见性
        self.content_area.visible = self.is_expanded

        # 调用回调函数通知父容器
        if self.on_toggle and self.page:  # 确保页面和控件都已挂载
            # print(f"[InterestMonitor] 调用回调函数通知父容器: {self.is_expanded}")
            self.on_toggle(self.is_expanded)

        # 更新UI
        if self.page:  # 确保页面存在再更新
            self.update()

    def did_mount(self):
        print("[InterestMonitor] 控件已挂载，启动日志读取任务")
        if self.page:
            # --- 首次加载历史想法 (可以在这里或 log_reader_loop 首次运行时加载) ---
            # self.page.run_task(self.load_and_process_log, initial_load=True) # 传递标志?
            self.log_reader_task = self.page.run_task(self.log_reader_loop)
            self.log_truncate_task = self.page.run_task(self.truncate_log_file_periodically) # 启动日志清理任务
            # self.page.run_task(self.update_charts) # update_charts 会在 loop 中调用
        else:
            print("[InterestMonitor] 错误: 无法访问 self.page 来启动后台任务")

    def will_unmount(self):
        print("[InterestMonitor] 控件将卸载，取消日志读取任务")
        if self.log_reader_task:
            self.log_reader_task.cancel()
            print("[InterestMonitor] 日志读取任务已取消 (will_unmount)")
        if self.log_truncate_task: # 新增：取消日志清理任务
            self.log_truncate_task.cancel()
            print("[InterestMonitor] 日志清理任务已取消 (will_unmount)")

    async def log_reader_loop(self):
        while True:
            try:
                await self.load_and_process_log()
                await self.update_charts()
            except asyncio.CancelledError:
                print("[InterestMonitor] 日志读取循环被取消")
                break
            except Exception as e:
                print(f"[InterestMonitor] 日志读取循环出错: {e}")
                traceback.print_exc()
                self.update_status(f"日志读取错误: {e}", ft.colors.ERROR)

            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

    async def truncate_log_file_periodically(self):
        """每隔一段时间清理日志文件顶部的内容。"""
        while True:
            await asyncio.sleep(LOG_TRUNCATE_INTERVAL_SECONDS)
            if not self.LOG_FILE_PATH or not os.path.exists(self.LOG_FILE_PATH):
                print(f"[LogTruncate] 日志文件路径未设置或文件不存在: {self.LOG_FILE_PATH}")
                continue
            
            print(f"[LogTruncate] 开始尝试清理日志文件: {self.LOG_FILE_PATH}")
            try:
                with open(self.LOG_FILE_PATH, "r+", encoding="utf-8") as f:
                    lines = f.readlines()
                    current_line_count = len(lines)

                    if current_line_count > LOG_TRUNCATE_THRESHOLD_LINES:
                        # 计算要保留的行数，是从底部往上数的 LOG_TRUNCATE_RETAIN_LINES 行
                        # 因此，要跳过顶部的 current_line_count - LOG_TRUNCATE_RETAIN_LINES 行
                        lines_to_skip = current_line_count - LOG_TRUNCATE_RETAIN_LINES
                        if lines_to_skip < 0: # 理论上不应发生，因为 current_line_count > THRESHOLD
                            lines_to_skip = 0 
                        
                        lines_to_keep = lines[lines_to_skip:]
                        
                        f.seek(0)  # 移动到文件开头
                        f.truncate() # 清空文件内容
                        f.writelines(lines_to_keep) # 写回剩余的行
                        print(f"[LogTruncate] 日志行数 {current_line_count} 超出 {LOG_TRUNCATE_THRESHOLD_LINES}。已清理，保留最新的 {len(lines_to_keep)} 行。")
                    else:
                        print(f"[LogTruncate] 日志行数 ({current_line_count}) 未超出 {LOG_TRUNCATE_THRESHOLD_LINES}，无需清理。")
            except asyncio.CancelledError:
                print("[LogTruncate] 日志清理任务被取消。")
                break # 退出循环
            except IOError as e:
                print(f"[LogTruncate] 清理日志文件时发生IO错误: {e}")
            except Exception as e:
                print(f"[LogTruncate] 清理日志文件时发生未知错误: {e}")
                traceback.print_exc()

    async def load_and_process_log(self):
        """读取并处理日志文件的新增内容。"""
        if not os.path.exists(self.LOG_FILE_PATH):
            self.update_status("日志文件未找到", ft.colors.ORANGE)
            return

        try:
            file_mod_time = os.path.getmtime(self.LOG_FILE_PATH)
            if file_mod_time <= self.last_log_read_time:
                return

            print(f"[InterestMonitor] 检测到日志文件更新 (修改时间: {file_mod_time}), 正在读取...", flush=True)

            new_stream_history = {}
            new_probability_history = {}
            new_stream_display_names = {}
            # 清理旧的子流状态，因为每次都重新读取文件
            self.stream_sub_minds.clear()
            self.stream_chat_states.clear()
            self.stream_threshold_status.clear()
            self.stream_last_active.clear()

            read_count = 0
            error_count = 0

            with open(self.LOG_FILE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    read_count += 1
                    try:
                        log_entry = json.loads(line.strip())
                        if not isinstance(log_entry, dict):
                            continue

                        entry_timestamp = log_entry.get("timestamp")
                        if entry_timestamp is None:
                            continue

                        # --- 处理主兴趣流 --- #
                        stream_id = log_entry.get("stream_id")
                        interest = log_entry.get("interest")
                        probability = log_entry.get("probability")  # 新增：获取概率

                        if stream_id is not None and interest is not None:
                            try:
                                interest_float = float(interest)
                                if stream_id not in new_stream_history:
                                    new_stream_history[stream_id] = []
                                # 避免重复添加相同时间戳的数据点
                                if (
                                    not new_stream_history[stream_id]
                                    or new_stream_history[stream_id][-1][0] < entry_timestamp
                                ):
                                    new_stream_history[stream_id].append((entry_timestamp, interest_float))
                            except (ValueError, TypeError):
                                pass  # 忽略无法转换的值

                        # --- 处理概率 --- #
                        if stream_id is not None and probability is not None:
                            try:
                                prob_float = float(probability)
                                if stream_id not in new_probability_history:
                                    new_probability_history[stream_id] = []
                                if (
                                    not new_probability_history[stream_id]
                                    or new_probability_history[stream_id][-1][0] < entry_timestamp
                                ):
                                    new_probability_history[stream_id].append((entry_timestamp, prob_float))
                            except (ValueError, TypeError):
                                pass  # 忽略无法转换的值

                        # --- 处理子流 (subflows) --- #
                        subflows = log_entry.get("subflows")
                        if not isinstance(subflows, list):
                            continue

                        for subflow_entry in subflows:
                            stream_id = subflow_entry.get("stream_id")
                            # 兼容两种字段名
                            interest = subflow_entry.get("interest", subflow_entry.get("interest_level"))
                            group_name = subflow_entry.get("group_name", stream_id)
                            # 兼容两种概率字段名
                            probability = subflow_entry.get("probability", subflow_entry.get("start_hfc_probability"))

                            if stream_id is None or interest is None:
                                continue
                            try:
                                interest_float = float(interest)
                            except (ValueError, TypeError):
                                continue

                            if stream_id not in new_stream_history:
                                new_stream_history[stream_id] = []
                                self.stream_details[stream_id] = {"group_name": group_name}  # 存储详情
                            # 避免重复添加相同时间戳的数据点
                            if (
                                not new_stream_history[stream_id]
                                or new_stream_history[stream_id][-1][0] < entry_timestamp
                            ):
                                new_stream_history[stream_id].append((entry_timestamp, interest_float))

                            # --- 处理子流概率 --- #
                            if probability is not None:
                                try:
                                    prob_float = float(probability)
                                    if stream_id not in new_probability_history:
                                        new_probability_history[stream_id] = []
                                    if (
                                        not new_probability_history[stream_id]
                                        or new_probability_history[stream_id][-1][0] < entry_timestamp
                                    ):
                                        new_probability_history[stream_id].append((entry_timestamp, prob_float))
                                except (ValueError, TypeError):
                                    pass  # 忽略无法转换的值

                            # --- 存储其他子流详情 (最新的会覆盖旧的) ---
                            self.stream_sub_minds[stream_id] = subflow_entry.get("sub_mind", "N/A")
                            self.stream_chat_states[stream_id] = subflow_entry.get("sub_chat_state", "N/A")
                            self.stream_threshold_status[stream_id] = subflow_entry.get("is_above_threshold", False)
                            self.stream_last_active[stream_id] = subflow_entry.get("chat_state_changed_time")

                    except json.JSONDecodeError:
                        error_count += 1
                        continue
                    except Exception as line_err:
                        print(f"处理日志行时出错: {line_err}")  # 打印行级错误
                        error_count += 1
                        continue

            # 更新状态
            self.stream_history = new_stream_history
            self.probability_history = new_probability_history
            self.stream_display_names = new_stream_display_names
            self.last_log_read_time = file_mod_time

            status_msg = f"日志读取于 {datetime.now().strftime('%H:%M:%S')}. 行数: {read_count}."
            if error_count > 0:
                status_msg += f" 跳过 {error_count} 无效行."
                self.update_status(status_msg, ft.colors.ORANGE)
            else:
                self.update_status(status_msg, ft.colors.GREEN)

            # 更新全局信息控件 (如果 page 存在)
            if self.page:
                # 更新全局状态信息
                if log_entry:  # Check if log_entry was populated
                    mai_state = log_entry.get("mai_state", "N/A")
                    # subflow_count = log_entry.get('subflow_count', '0')

                    # 获取当前时间和行数信息，格式化为状态信息的一部分
                    current_time = datetime.now().strftime("%H:%M:%S")
                    status_info = f"读取于{current_time}"
                    if error_count > 0:
                        status_info += f" (跳过 {error_count} 行)"

                    # 将所有信息合并到一行显示
                    if mai_state != "N/A":
                        if mai_state == "PEEKING":
                            mai_state_str = "看一眼手机"
                        elif mai_state == "NORMAL_CHAT":
                            mai_state_str = "正常看手机"
                        elif mai_state == "FOCUSED_CHAT":
                            mai_state_str = "专心看手机"
                        elif mai_state == "OFFLINE":
                            mai_state_str = "不在线"

                    combined_info = f"{status_info} | 状态: {mai_state_str}"
                    self.global_mai_state_text.value = combined_info
                    self.global_info_row.update()

                    # 更新状态文本的颜色
                    color = ft.colors.GREEN if error_count == 0 else ft.colors.ORANGE
                    self.global_mai_state_text.color = color

            # 更新下拉列表选项
            await self.update_dropdown_options()

        except IOError as e:
            print(f"读取日志文件时发生 IO 错误: {e}")
            self.update_status(f"日志 IO 错误: {e}", ft.colors.ERROR)
        except Exception as e:
            print(f"处理日志时发生意外错误: {e}")
            traceback.print_exc()
            self.update_status(f"处理日志时出错: {e}", ft.colors.ERROR)

    async def update_charts(self):
        all_series = []
        legend_items = []  # 存储图例控件

        # 检查是否有足够的数据生成图表
        if not self.stream_history:
            # print("[InterestMonitor] 警告: 没有流历史数据可用于生成图表")
            self.update_status("无图表数据可用", ft.colors.ORANGE)
            # 清空图表
            self.main_chart.data_series = []
            self.legend_column.controls = []
            self.update()
            return

        active_streams_sorted = sorted(
            self.stream_history.items(), key=lambda item: item[1][-1][1] if item[1] else -1, reverse=True
        )[:MAX_STREAMS_TO_DISPLAY]

        # 调试信息
        print(f"[InterestMonitor] 有 {len(active_streams_sorted)} 个活跃流可用于图表")
        for stream_id, history in active_streams_sorted:
            print(f"[InterestMonitor] 流 {stream_id}: {len(history)} 个数据点")

        # 清空现有图表数据和图例，为新的数据做准备
        self.main_chart.data_series = []
        self.legend_column.controls = []
        # 如果当前没有选择特定的流查看详情，也清空详情图表和文本
        if not self.selected_stream_id_for_details:
            self.detail_chart_combined.data_series = [] # 清空详情图表的数据系列
            self.detail_chart_combined.min_x = None     # 重置详情图表的X轴范围
            self.detail_chart_combined.max_x = None
            await self.update_detail_texts(None) # 清空详情区域的文本信息

        # self.update() # 在这里更新可能会导致图表在填充数据前短暂显示为空，先注释掉
        # return  # <--- 移除这个过早的 return 语句

        # --- 基于过滤后的数据点重新构建图表系列 ---
        current_time_for_cutoff = time.time()
        cutoff_timestamp = current_time_for_cutoff - CHART_DISPLAY_TIMESPAN_SECONDS

        for stream_id, history in active_streams_sorted:
            if not history:
                continue
            try:
                mpl_dates = [ts for ts, _ in history]
                interests = [interest for _, interest in history]
                if not mpl_dates:
                    continue

                # 为颜色分配固定的颜色，如果不存在
                if stream_id not in self.stream_colors:
                    self.stream_colors[stream_id] = get_random_flet_color()

                # 获取或设置显示名称
                if stream_id not in self.stream_display_names:
                    group_name = self.stream_details.get(stream_id, {}).get("group_name", stream_id)
                    self.stream_display_names[stream_id] = group_name

                data_points = [ft.LineChartDataPoint(x=ts, y=interest) for ts, interest in zip(mpl_dates, interests)]
                all_series.append(
                    ft.LineChartData(
                        data_points=data_points,
                        color=self.stream_colors.get(stream_id, ft.colors.BLACK),
                        stroke_width=2,
                    )
                )
                # --- 创建图例项 ---
                legend_color = self.stream_colors.get(stream_id, ft.colors.BLACK)
                display_name = self.stream_display_names.get(stream_id, stream_id)
                legend_items.append(
                    ft.Row(
                        controls=[
                            ft.Container(width=10, height=10, bgcolor=legend_color, border_radius=2),
                            ft.Text(display_name, size=10, overflow=ft.TextOverflow.ELLIPSIS),
                        ],
                        spacing=5,
                        alignment=ft.MainAxisAlignment.START,
                    )
                )
            except Exception as plot_err:
                print(f"绘制主图表/图例时跳过 Stream {stream_id}: {plot_err}")
                traceback.print_exc()  # 添加完整的错误堆栈
                continue

        # --- 更新主图表 ---
        self.main_chart.data_series = all_series
        self.main_chart.min_y = 0
        self.main_chart.max_y = 10
        # self.main_chart.min_x = min_ts # min_x 和 max_x 将由 get_time_range 基于过滤数据设定
        # self.main_chart.max_x = max_ts

        # --- 计算主图表的X轴范围 --- #
        # 我们需要基于 *所有活跃且过滤后有数据的流* 来确定总的X轴范围
        all_filtered_history_for_main_chart = {}
        for stream_id, history_data in active_streams_sorted: # active_streams_sorted 已经是过滤过显示数量的
            if stream_id in self.stream_history and self.stream_history[stream_id]:
                all_filtered_history_for_main_chart[stream_id] = self.stream_history[stream_id]
        
        min_x_main, max_x_main = self.get_time_range(all_filtered_history_for_main_chart, force_recent_timespan_seconds=CHART_DISPLAY_TIMESPAN_SECONDS)
        self.main_chart.min_x = min_x_main
        self.main_chart.max_x = max_x_main

        # --- 更新图例 ---
        self.legend_column.controls = legend_items

        # 只有在选择了流的情况下更新详情图表
        if self.selected_stream_id_for_details:
            await self.update_detail_charts(self.selected_stream_id_for_details)
        else:
            print("[InterestMonitor] 未选择流，跳过详情图表更新")

        if self.page:
            # 更新整个控件，包含图表和图例的更新
            self.update()
        else:
            print("[InterestMonitor] 警告: self.page 为 None，无法更新图表 UI")

    async def update_detail_charts(self, stream_id):
        combined_series = []
        min_ts_detail, max_ts_detail = None, None

        # --- 增加检查：如果没有选择流ID或流ID不在历史记录中，则直接返回
        if not stream_id or (stream_id not in self.stream_history and stream_id not in self.probability_history):
            print(f"[InterestMonitor] 详细图表：没有找到流ID或未选择流ID: {stream_id}")
            # 清空图表
            self.detail_chart_combined.data_series = []
            self.detail_chart_combined.min_x = None # 清除min/max x,y
            self.detail_chart_combined.max_x = None
            self.detail_chart_combined.min_y = 0
            self.detail_chart_combined.max_y = 10

            # 确保更新详情文本，清空信息
            await self.update_detail_texts(None)
            if self.page and self.detail_chart_combined.page: # 确保控件已挂载
                self.detail_chart_combined.update()
            return

        current_time_for_cutoff = time.time()
        cutoff_timestamp = current_time_for_cutoff - CHART_DISPLAY_TIMESPAN_SECONDS

        # --- 兴趣度图 ---
        filtered_interest_history = []
        if stream_id and stream_id in self.stream_history and self.stream_history[stream_id]:
            filtered_interest_history = [(ts, val) for ts, val in self.stream_history[stream_id] if ts >= cutoff_timestamp]
            if filtered_interest_history:
                try:
                    mpl_dates = [ts for ts, _ in filtered_interest_history]
                    interests = [interest for _, interest in filtered_interest_history]
                    interest_data_points = [
                        ft.LineChartDataPoint(x=ts, y=interest) for ts, interest in zip(mpl_dates, interests)
                    ]
                    combined_series.append(
                        ft.LineChartData(
                            data_points=interest_data_points,
                            color=self.stream_colors.get(stream_id, ft.colors.BLUE),
                            stroke_width=2,
                        )
                    )
                except Exception as plot_err:
                    print(f"绘制详情兴趣图时出错 Stream {stream_id}: {plot_err}")

        # --- 概率图 ---
        filtered_probability_history = []
        if stream_id and stream_id in self.probability_history and self.probability_history[stream_id]:
            filtered_probability_history = [(ts, val) for ts, val in self.probability_history[stream_id] if ts >= cutoff_timestamp]
            if filtered_probability_history:
                try:
                    prob_dates = [ts for ts, _ in filtered_probability_history]
                    probabilities = [prob for _, prob in filtered_probability_history]
                    # 调整HFC概率值到兴趣度的比例范围，便于在一个图表中显示
                    # 兴趣度范围0-10，将概率值x10
                    scaled_probabilities = [prob * 10 for prob in probabilities]

                    probability_data_points = [
                        ft.LineChartDataPoint(x=ts, y=prob) for ts, prob in zip(prob_dates, scaled_probabilities)
                    ]
                    combined_series.append(
                        ft.LineChartData(
                            data_points=probability_data_points,
                            color=ft.colors.GREEN,
                            stroke_width=2,
                        )
                    )
                except Exception as plot_err:
                    print(f"绘制详情概率图时出错 Stream {stream_id}: {plot_err}")
        
        # --- 计算详情图表的X轴范围 --- #
        # 合并过滤后的兴趣度和概率历史数据来确定X轴
        detail_chart_source_data = {}
        if filtered_interest_history:
            detail_chart_source_data[f"{stream_id}_interest"] = filtered_interest_history
        if filtered_probability_history:
             # 使用不同的key，即使是同一个stream_id，因为get_time_range期望value是(ts, val)列表
            detail_chart_source_data[f"{stream_id}_prob"] = filtered_probability_history

        if not detail_chart_source_data: # 如果过滤后两个都没有数据
            print(f"[InterestMonitor] 详细图表：流 {stream_id} 在过去10分钟内无数据")
            self.detail_chart_combined.data_series = [] # 清空系列
            min_ts_detail, max_ts_detail = self.get_time_range({}, force_recent_timespan_seconds=CHART_DISPLAY_TIMESPAN_SECONDS)
        else:
            min_ts_detail, max_ts_detail = self.get_time_range(detail_chart_source_data, force_recent_timespan_seconds=CHART_DISPLAY_TIMESPAN_SECONDS)

        # 更新合并图表
        self.detail_chart_combined.data_series = combined_series
        self.detail_chart_combined.min_y = 0
        self.detail_chart_combined.max_y = 10
        self.detail_chart_combined.min_x = min_ts_detail
        self.detail_chart_combined.max_x = max_ts_detail

        await self.update_detail_texts(stream_id)

    async def update_dropdown_options(self):
        current_value = self.stream_dropdown.value
        options = []
        valid_stream_ids = set()

        # 调试信息
        print(f"[InterestMonitor] 更新流下拉列表，当前有 {len(self.stream_history)} 个流")

        # 确保所有流都有显示名称
        for stream_id in self.stream_history.keys():
            if stream_id not in self.stream_display_names:
                # 如果没有显示名称，使用group_name或stream_id
                group_name = self.stream_details.get(stream_id, {}).get("group_name", stream_id)
                self.stream_display_names[stream_id] = group_name
                print(f"[InterestMonitor] 为流 {stream_id} 设置显示名称: {group_name}")

        # 排序所有流数据用于下拉列表
        sorted_items = sorted(
            [
                (stream_id, self.stream_display_names.get(stream_id, stream_id))
                for stream_id in self.stream_history.keys()
            ],
            key=lambda item: item[1],  # 按显示名称排序
        )

        for stream_id, display_name in sorted_items:
            if stream_id in self.stream_history and self.stream_history[stream_id]:
                option_text = f"{display_name}"
                options.append(ft.dropdown.Option(key=stream_id, text=option_text))
                valid_stream_ids.add(stream_id)
                print(f"[InterestMonitor] 添加流选项: {stream_id} ({display_name})")

        self.stream_dropdown.options = options

        # 如果当前值无效，选择第一个选项或清空
        if not current_value or current_value not in valid_stream_ids:
            new_value = options[0].key if options else None
            if self.stream_dropdown.value != new_value:
                print(f"[InterestMonitor] 设置新的选中流: {new_value}")
                self.stream_dropdown.value = new_value
                self.selected_stream_id_for_details = new_value
                await self.update_detail_charts(new_value)

        # 确保按钮状态正确
        self.control_button.disabled = not self.stream_dropdown.value

        if self.page and self.stream_dropdown.page:
            self.stream_dropdown.update()
            self.control_button.update()

    async def on_stream_selected(self, e):
        selected_id = e.control.value  # value 应该是 stream_id (key)
        print(f"[InterestMonitor] 选择了 Stream ID: {selected_id}")
        if self.selected_stream_id_for_details != selected_id:
            self.selected_stream_id_for_details = selected_id
            # 启用控制按钮
            self.control_button.disabled = selected_id is None
            await self.update_detail_charts(selected_id)
            # Dropdown 更新是自动的，但图表和文本需要手动触发父容器更新
            if self.page:
                self.update()

    async def update_detail_texts(self, stream_id):
        if not self.detail_texts or not hasattr(self.detail_texts, "controls") or len(self.detail_texts.controls) < 1:
            print("[InterestMonitor] 错误：detail_texts 未正确初始化或控件不足")
            return

        if stream_id and stream_id in self.stream_history:
            sub_mind = self.stream_sub_minds.get(stream_id, "N/A")
            chat_state = self.stream_chat_states.get(stream_id, "N/A")
            last_active_ts = self.stream_last_active.get(stream_id)
            last_active_str = format_timestamp(last_active_ts)

            # 合并详情为一行
            detail_text = f"状态: {chat_state} | 最后活跃: {last_active_str}"
            if sub_mind and sub_mind != "N/A" and sub_mind.strip():
                detail_text = f"想法: {sub_mind} | {detail_text}"

            self.detail_texts.controls[0].value = detail_text
            self.detail_texts.controls[0].tooltip = detail_text  # 完整文本作为tooltip
        else:
            # 默认显示
            self.detail_texts.controls[0].value = "状态: 无 | 最后活跃: 无"
            self.detail_texts.controls[0].tooltip = "暂无详细信息"

        if self.page and self.detail_texts.page:  # 确保控件已挂载再更新
            self.detail_texts.update()

    def update_status(self, message: str, color: str = ft.colors.SECONDARY):
        max_len = 150
        display_message = (message[:max_len] + "...") if len(message) > max_len else message

        # 保留当前状态信息的一部分（如果存在）
        if "|" in self.global_mai_state_text.value:
            status_part = self.global_mai_state_text.value.split("|")[1].strip()
            self.status_text.value = f"{display_message} | {status_part}"
        else:
            self.status_text.value = display_message

        self.status_text.color = color
        if self.page and self.status_text.page:
            self.status_text.update()

    def get_time_range(self, history_dict, is_prob=False, force_recent_timespan_seconds=None):
        """获取所有数据点的时间范围，确保即使没有数据也能返回有效的时间范围"""
        all_ts = []
        # target_history_key = self.probability_history if is_prob else self.stream_history
        # ^^^ is_prob is not used anymore as history_dict now contains pre-selected data

        try:
            for _stream_id, history_data_list in history_dict.items(): # history_dict的value已经是 [(ts,val),...]
                if history_data_list:
                    all_ts.extend([ts for ts, _ in history_data_list])

            now = time.time()
            if not all_ts: # 如果没有数据点
                if force_recent_timespan_seconds:
                    # print(f"[get_time_range] 无数据点，强制使用最近 {force_recent_timespan_seconds} 秒范围")
                    return now - force_recent_timespan_seconds, now
                else:
                    # print(f"[get_time_range] 无数据点，使用默认1小时前回溯")
                    return now - 3600, now + 60 # 默认1小时前回溯, 1分钟余量

            valid_ts = sorted([ts for ts in all_ts if isinstance(ts, (int, float))])
            if not valid_ts:
                if force_recent_timespan_seconds:
                    # print(f"[get_time_range] 无有效数据点，强制使用最近 {force_recent_timespan_seconds} 秒范围")
                    return now - force_recent_timespan_seconds, now
                else:
                    # print(f"[get_time_range] 无有效数据点，使用默认1小时前回溯")
                    return now - 3600, now + 60

            actual_min_ts = valid_ts[0]
            actual_max_ts = valid_ts[-1]

            if force_recent_timespan_seconds:
                # 如果强制时间跨度，max_x 是 actual_max_ts (或当前时间如果前者更早)
                # min_x 是 max_x - timespan，但不能早于 actual_min_ts
                current_max_x = max(actual_max_ts, now - 5) # 给几秒buffer，防止图表看起来太空
                current_min_x = current_max_x - force_recent_timespan_seconds
                # print(f"[get_time_range] 强制范围: current_max_x={current_max_x}, current_min_x={current_min_x}, actual_min_ts={actual_min_ts}")
                # 确保 min_x 不会比数据集中最早的时间点还早
                # return max(current_min_x, actual_min_ts), current_max_x
                # 修正：min_x 可以比 actual_min_ts 早，这样X轴的起点是固定的10分钟前
                # 但如果 actual_max_ts 本身就很早 (例如1小时前的数据)，那么 min_x 应该基于 actual_max_ts
                effective_max_x = actual_max_ts # 使用数据中的最新点作为右边界
                effective_min_x = effective_max_x - force_recent_timespan_seconds
                # 如果数据中的最早点比计算出的10分钟前的点还要晚，那么就用数据中的最早点作为左边界
                # 这样可以避免左边有大量空白，如果数据本身不足10分钟的话
                # final_min_x = max(effective_min_x, actual_min_ts) # 旧逻辑，会导致短数据被拉伸
                # print(f"[get_time_range] 强制范围: effective_max_x={effective_max_x}, effective_min_x={effective_min_x}")
                return effective_min_x, effective_max_x
            else:
                # 默认行为: 基于数据范围加padding
                padding = 0
                if actual_min_ts == actual_max_ts:
                    # print(f"[get_time_range] 单点数据，padding 60s")
                    padding = 60
                else:
                    # print(f"[get_time_range] 多点数据，padding 5%")
                    padding = (actual_max_ts - actual_min_ts) * 0.05
                
                # print(f"[get_time_range] 默认范围: min={actual_min_ts - padding}, max={actual_max_ts + padding}")
                return actual_min_ts - padding, actual_max_ts + padding

        except Exception as e:
            now = time.time()
            print(f"[InterestMonitor] 获取时间范围时出错: {e}")
            traceback.print_exc()
            if force_recent_timespan_seconds:
                return now - force_recent_timespan_seconds, now
            return now - 3600, now + 60 # 默认回溯1小时