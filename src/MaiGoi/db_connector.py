import os
from pymongo import MongoClient
from pymongo.database import Database
from dotenv import load_dotenv # 用于加载 .env 文件
from pathlib import Path
from typing import Optional

# Rich traceback (可选, 但对于调试有益)
try:
    from rich.traceback import install
    install(extra_lines=3)
except ImportError:
    pass # 如果没有安装 rich，则跳过

# --- 全局变量 ---
_client = None
_db_instance = None # 重命名以避免与 pymongo.database.Database 混淆

# --- .env 文件加载 ---
# 假设 .env 文件与 main.py 在同一级别或项目的根目录
# 或者，如果 .env 文件固定在 mmc_path 下，则在 get_db 中处理
# 这里我们先尝试在模块加载时加载项目根目录的 .env (如果存在)
# 注意：Flet应用的当前工作目录可能在运行时有所不同，
# 因此，依赖 app_state.mmc_path (在 get_db 中处理) 可能更可靠。

# env_path = Path('.') / '.env' # 尝试加载当前工作目录的 .env
# load_dotenv(dotenv_path=env_path)

def _create_database_instance(mmc_path: Path):
    """
    根据环境变量创建 MongoDB 客户端实例。
    优先使用 MONGODB_URI，然后是独立的主机/端口/凭据。
    .env 文件应该位于 mmc_path 目录下。
    """
    # --- 加载 .env 文件 (如果 mmc_path 下存在) ---
    # 这是更可靠的加载 .env 的位置，因为它基于 bot 脚本的路径
    env_file_in_mmc = mmc_path / ".env"
    if env_file_in_mmc.is_file():
        load_dotenv(dotenv_path=env_file_in_mmc, override=True) # override=True 确保环境变量被更新
        print(f"[DB Connector] 从 {env_file_in_mmc} 加载了 .env 文件")
    else:
        print(f"[DB Connector] 警告: 在 {env_file_in_mmc} 未找到 .env 文件。将依赖现有环境变量或默认值。")

    uri = os.getenv("MONGODB_URI")
    host = os.getenv("MONGODB_HOST", "127.0.0.1")
    port = int(os.getenv("MONGODB_PORT", "27017"))
    username = os.getenv("MONGODB_USERNAME")
    password = os.getenv("MONGODB_PASSWORD")
    auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin") # 默认 authSource 通常是 admin

    if uri:
        if uri.startswith(("mongodb://", "mongodb+srv://")):
            print(f"[DB Connector] 使用 URI 连接 MongoDB: {uri}")
            return MongoClient(uri)
        else:
            print("[DB Connector] 错误: 无效的 MongoDB URI 格式。")
            raise ValueError(
                "无效的 MongoDB URI 格式。 URI 必须以 'mongodb://' 或 'mongodb+srv://' 开头。"
            )

    print(f"[DB Connector] 使用 Host/Port 连接 MongoDB: {host}:{port}")
    if username and password:
        print(f"[DB Connector] 使用认证: 用户名={username}, authSource={auth_source}")
        return MongoClient(host, port, username=username, password=password, authSource=auth_source)
    
    print("[DB Connector] 使用无认证连接")
    return MongoClient(host, port)


def get_gui_db(mmc_path: Path, db_name_override: Optional[str] = None) -> Database:
    """
    获取 GUI 使用的数据库连接实例，采用懒加载方式。
    mmc_path: bot 脚本所在的根目录，用于定位 .env 文件。
    db_name_override: 可选，用于覆盖从 .env 或默认的数据库名称。
    """
    global _client, _db_instance

    if _client is None:
        print("[DB Connector] 初始化 MongoDB 客户端...")
        try:
            _client = _create_database_instance(mmc_path)
            # 检查连接是否成功 (可选，但推荐)
            _client.admin.command('ping') # 发送一个ping命令
            print("[DB Connector] MongoDB 客户端连接成功。")
        except Exception as e:
            print(f"[DB Connector] 错误: 连接 MongoDB 失败: {e}")
            _client = None # 连接失败，重置 client
            # 可以选择抛出异常或返回 None，这里选择让 _db_instance 为 None
            # 以便调用方可以检查
            return None # 或者 raise e

    if _db_instance is None and _client is not None: # 只有在客户端连接成功后才获取数据库实例
        # 从环境变量获取数据库名称，如果未设置则使用默认名称 "MaiLauncherDB"
        db_name_to_use = db_name_override if db_name_override else os.getenv("DATABASE_NAME", "MaiLauncherDB")
        print(f"[DB Connector] 获取数据库实例: {db_name_to_use}")
        _db_instance = _client[db_name_to_use]
    
    return _db_instance

class GUIDBWrapper:
    """
    数据库代理类，为 GUI 实现懒加载数据库访问。
    需要 mmc_path 来定位 .env 文件。
    """
    def __init__(self, mmc_path_provider):
        """
        mmc_path_provider: 一个函数或可调用对象，用于获取 mmc_path。
                           例如: lambda: app_state.mmc_path
        """
        self._mmc_path_provider = mmc_path_provider
        self._db_instance_internal = None

    def _get_actual_db(self) -> Database:
        if self._db_instance_internal is None:
            mmc_path = self._mmc_path_provider()
            if not mmc_path:
                print("[DB Wrapper] 错误: mmc_path 未提供，无法初始化数据库。")
                return None # 或者抛出异常
            self._db_instance_internal = get_gui_db(Path(mmc_path))
        return self._db_instance_internal

    def __getattr__(self, name):
        db = self._get_actual_db()
        if db is None:
            raise AttributeError(f"数据库未初始化或连接失败，无法获取属性 '{name}'")
        return getattr(db, name)

    def __getitem__(self, key):
        db = self._get_actual_db()
        if db is None:
            raise KeyError(f"数据库未初始化或连接失败，无法获取集合 '{key}'")
        return db[key]

# 注意：全局数据库访问点 gui_db 的初始化需要 mmc_path。
# 这通常在 AppState 可用后进行。
# 因此，我们不在模块级别直接创建 GUIDBWrapper 实例，
# 而是在 main.py 中，当 AppState 和 mmc_path 可用时创建。

# 例如，在 main.py 中可以这样做：
# app_state.db = GUIDBWrapper(lambda: app_state.mmc_path)
# 然后通过 app_state.db.collection_name 访问

def close_db_connection():
    """关闭 MongoDB 客户端连接（如果已打开）。"""
    global _client
    if _client:
        print("[DB Connector] 关闭 MongoDB 客户端连接...")
        _client.close()
        _client = None
        _db_instance = None # 清理数据库实例引用
        print("[DB Connector] MongoDB 客户端连接已关闭。")

# 添加新的函数或方法 