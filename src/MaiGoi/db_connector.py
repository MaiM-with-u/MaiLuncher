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
        print(f"[DB Connector] 错误: 在 {env_file_in_mmc} 未找到 .env 文件。无法配置数据库连接。")
        return None # 如果 .env 文件未找到，则不尝试连接

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

    print(f"[DB Connector] get_gui_db 被调用，mmc_path={mmc_path}, _client={_client is not None}")

    if _client is None:
        print("[DB Connector] 初始化 MongoDB 客户端...")
        try:
            _client = _create_database_instance(mmc_path)
            
            # 检查连接结果
            if _client is None:
                print("[DB Connector] 注意: _create_database_instance 返回 None (可能是 .env 不存在)")
                return None
                
            # 检查连接是否成功 (可选，但推荐)
            _client.admin.command('ping') # 发送一个ping命令
            print(f"[DB Connector] MongoDB 客户端连接成功。ID: {id(_client)}")
        except Exception as e:
            print(f"[DB Connector] 错误: 连接 MongoDB 失败: {e}")
            _client = None # 连接失败，重置 client
            return None

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
        print("[DB Wrapper] 初始化 GUIDBWrapper 实例")

    def _get_actual_db(self) -> Database:
        """获取实际的数据库实例，如果没有则尝试创建。"""
        # 获取当前的 mmc_path
        mmc_path = self._mmc_path_provider()
        if not mmc_path:
            print("[DB Wrapper] 错误: mmc_path 未提供，无法初始化数据库。")
            return None
            
        print(f"[DB Wrapper] _get_actual_db 调用，当前 mmc_path={mmc_path}, 忽略内部缓存")
        
        # 始终尝试新建连接，不使用内部缓存
        # 这是一种新的更安全的方法，确保即使 full_database_reset 后也能重新连接
        try:
            # 直接返回新获取的实例，不存储在 self._db_instance_internal
            db_instance = get_gui_db(Path(mmc_path))
            if db_instance is None:
                print("[DB Wrapper] 注意: get_gui_db 返回 None，可能是因为 .env 不存在或连接失败。")
            else:
                print(f"[DB Wrapper] 成功获取数据库实例，ID: {id(db_instance)}")
            return db_instance
        except Exception as ex:
            print(f"[DB Wrapper] 获取数据库实例出错: {ex}")
            return None

    def __getattr__(self, name):
        """当访问不存在的属性时，尝试从数据库实例获取。"""
        db = self._get_actual_db()
        if db is None:
            err_msg = f"数据库未初始化或连接失败，无法获取属性 '{name}'"
            print(f"[DB Wrapper] 错误: {err_msg}")
            raise AttributeError(err_msg)
        return getattr(db, name)

    def __getitem__(self, key):
        """当使用字典方式访问时，尝试从数据库实例获取集合。"""
        db = self._get_actual_db()
        if db is None:
            err_msg = f"数据库未初始化或连接失败，无法获取集合 '{key}'"
            print(f"[DB Wrapper] 错误: {err_msg}")
            raise KeyError(err_msg)
        return db[key]

    def reset_connection(self):
        """重置包装器内部缓存的数据库实例。"""
        if self._db_instance_internal is not None:
            print(f"[DB Wrapper] 内部数据库实例缓存已重置，原实例 ID: {id(self._db_instance_internal)}")
        else:
            print("[DB Wrapper] 内部数据库实例缓存已重置 (原本就是 None)")
        self._db_instance_internal = None

def close_db_connection():
    """关闭 MongoDB 客户端连接（如果已打开）。"""
    global _client, _db_instance
    if _client:
        client_id = id(_client)
        print(f"[DB Connector] 正在关闭 MongoDB 客户端连接... ID: {client_id}")
        try:
            _client.close()
            print(f"[DB Connector] MongoDB 客户端连接成功关闭，ID: {client_id}")
        except Exception as e:
            print(f"[DB Connector] 关闭客户端连接时出错: {e}")
        finally:
            _client = None
            _db_instance = None  
            print("[DB Connector] 全局客户端和数据库实例引用已清除")
    else:
        print("[DB Connector] 没有活动的全局 MongoDB 客户端可关闭")

def full_database_reset(db_wrapper_instance = None):
    """
    执行数据库连接的完全重置。
    关闭全局客户端并重置 GUIDBWrapper (如果提供) 的内部缓存。
    
    注意: 由于修改了 GUIDBWrapper._get_actual_db 方法使其不再使用缓存，
          调用 reset_connection 主要是为了保持兼容性和完整性。
    """
    global _client, _db_instance

    print("[DB Connector] 正在执行数据库完全重置...")
    # 1. 关闭全局 MongoDB 客户端连接 (与 close_db_connection 逻辑类似)
    if _client:
        client_id = id(_client)
        print(f"[DB Connector] 正在关闭现有的 MongoDB 客户端连接... ID: {client_id}")
        try:
            _client.close()
            print(f"[DB Connector] MongoDB 客户端连接成功关闭，ID: {client_id}")
        except Exception as e:
            print(f"[DB Connector] 关闭客户端连接时出错: {e}")
        finally:
            _client = None
            _db_instance = None
            print("[DB Connector] 全局客户端和数据库实例引用已清除") 
    else:
        print("[DB Connector] 没有活动的全局 MongoDB 客户端可关闭")

    # 2. 如果提供了 GUIDBWrapper 实例，则重置其内部缓存
    # 注意: 现在的 GUIDBWrapper._get_actual_db 不再使用缓存，这一步主要是为了保持兼容性
    if db_wrapper_instance is not None:
        if isinstance(db_wrapper_instance, GUIDBWrapper):
            print("[DB Connector] 正在重置 GUIDBWrapper 内部缓存... (尽管现在不再使用缓存)")
            db_wrapper_instance.reset_connection() 
        else:
            print(f"[DB Connector] 警告: 提供的 db_object 不是 GUIDBWrapper 的实例。类型: {type(db_wrapper_instance)}。无法重置其缓存。")
    else:
        print("[DB Connector] 注意: 未提供 GUIDBWrapper 实例，仅重置了全局连接")

# 添加新的函数或方法 