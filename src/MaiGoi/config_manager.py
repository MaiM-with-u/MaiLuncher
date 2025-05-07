import toml
from loguru import logger
import tomlkit
from pathlib import Path
import os
from typing import Dict, Any, Optional, List, Tuple

CONFIG_DIR = Path("config")
# Define default filenames for different config types
CONFIG_FILES = {"gui": "gui_config.toml", "lpmm": "lpmm_config.toml", "bot": "bot_config.toml"}
DEFAULT_GUI_CONFIG = {
    "adapters": [],
    "theme": "System",
    "subprocess_encoding": "utf-8",
    "python_path": "",
    "bot_script_path": "bot.py"
}  # Add default theme

# 全局变量跟踪已使用的配置路径
LAST_USED_CONFIG_PATHS = {}


# 添加新函数，验证配置文件一致性
def verify_config_consistency() -> List[Tuple[str, Path, bool]]:
    """验证所有配置文件路径是否一致存在，返回问题列表"""
    results = []
    
    # 检查默认路径和app_state.bot_base_dir路径（如果有）
    try:
        from src.MaiGoi.state import app_state
        has_app_state = True
    except (ImportError, AttributeError):
        has_app_state = False
    
    # 检查默认路径
    default_path = Path(__file__).parent.parent.parent / CONFIG_DIR
    default_exists = default_path.exists()
    results.append(("默认配置目录", default_path, default_exists))
    
    # 检查bot_base_dir
    if has_app_state and hasattr(app_state, 'bot_base_dir') and app_state.bot_base_dir:
        bot_config_path = Path(app_state.bot_base_dir) / CONFIG_DIR
        bot_path_exists = bot_config_path.exists()
        results.append(("Bot配置目录", bot_config_path, bot_path_exists))
    
    # 检查最后使用的配置路径
    for config_type, path in LAST_USED_CONFIG_PATHS.items():
        path_exists = Path(path).exists() if path else False
        results.append((f"最后使用的{config_type}配置", Path(path) if path else None, path_exists))
    
    return results


def get_config_path(config_type: str, base_dir: Optional[Path] = None) -> Optional[Path]:
    """
    获取配置文件路径.
    - GUI配置: 相对于当前工作目录 (e.g., <project_root>/config/gui_config.toml).
    - 其他配置: 相对于提供的 base_dir (e.g., <base_dir>/config/xxx_config.toml).
    """
    filename = CONFIG_FILES.get(config_type)
    if not filename:
        logger.error(f"未知的配置类型: '{config_type}'")
        return None

    if config_type == "gui":
        # GUI配置路径固定为 <cwd>/config/gui_config.toml
        # os.chdir() 应该在 main.py 中设置
        config_path = Path.cwd() / CONFIG_DIR / filename
        logger.debug(f"GUI配置路径 (基于 CWD): {config_path}")
        return config_path
    else:
        # 其他配置类型需要 base_dir
        if not base_dir:
            logger.error(f"配置类型 '{config_type}' 需要 'base_dir' 参数。")
            return None
        try:
            # 确保 base_dir 是绝对路径，如果它还不是
            abs_base_dir = Path(base_dir).resolve()
            config_path = abs_base_dir / CONFIG_DIR / filename
            logger.debug(f"'{config_type}' 配置路径 (基于 base_dir '{abs_base_dir}'): {config_path}")
            return config_path
        except Exception as e:
            logger.error(f"为 '{config_type}' 构建配置路径时出错，base_dir '{base_dir}': {e}")
            return None


def load_config(config_type: str, base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """从指定的TOML文件类型加载配置."""
    config_path = get_config_path(config_type, base_dir=base_dir)
    if not config_path:
        return {}

    logger.info(f"尝试从 '{config_path}' 加载 '{config_type}' 配置")
    default_config_to_use = DEFAULT_GUI_CONFIG if config_type == "gui" else {}

    # 对于非GUI配置，如果文件不存在，不创建，直接返回空字典
    if config_type != "gui" and not config_path.is_file():
        logger.warning(f"配置文件 '{config_path}' (类型: {config_type}) 未找到。不创建，返回空配置。")
        return {}

    try:
        if config_type == "gui":
            # 仅为GUI配置创建父目录和默认文件
            config_path.parent.mkdir(parents=True, exist_ok=True)
            if not config_path.is_file():
                logger.info(f"GUI配置文件 '{config_path}' 未找到，使用默认值创建。")
                save_config(default_config_to_use.copy(), config_type="gui", base_dir=None) # base_dir is not used for GUI save
                return default_config_to_use.copy()

        # 此时，对于GUI，文件肯定存在（或已创建）
        # 对于其他类型，我们已检查过文件存在性
        if config_path.is_file(): # 双重检查，主要针对非GUI路径（尽管上面已经检查过）
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = toml.load(f)
            logger.info(f"'{config_type}' 配置从 '{config_path}' 加载成功。")

            if config_type == "gui":
                updated = False
                for key, default_value in DEFAULT_GUI_CONFIG.items():
                    if key not in config_data:
                        logger.info(f"GUI配置中缺少键 '{key}'，添加默认值: '{default_value}'")
                        config_data[key] = default_value
                        updated = True
            return config_data
        else:
            # 此分支理论上不应为GUI执行到，对于其他类型，已在开头处理
            logger.warning(f"配置文件 '{config_path}' (类型: {config_type}) 最终未找到。")
            return default_config_to_use.copy() if config_type == "gui" else {}

    except toml.TomlDecodeError:
        logger.error(f"解码TOML文件 '{config_path}' (类型: {config_type}) 时出错。返回默认/空配置。")
        return default_config_to_use.copy() if config_type == "gui" else {}
    except Exception as e:
        logger.error(f"加载 '{config_type}' 配置 '{config_path}' 时发生意外错误: {e}")
        import traceback
        traceback.print_exc()
        return default_config_to_use.copy() if config_type == "gui" else {}


def save_config(config_data: Dict[str, Any], config_type: str, base_dir: Optional[Path] = None) -> bool:
    """将配置字典保存到指定的TOML文件类型."""
    config_path = get_config_path(config_type, base_dir=base_dir)
    if not config_path:
        # get_config_path 中已记录错误
        return False

    logger.info(f"尝试将 '{config_type}' 配置保存到 '{config_path}'")

    if config_type == "gui":
        # 确保GUI配置中的所有默认键都存在
        for key, default_value in DEFAULT_GUI_CONFIG.items():
            config_data.setdefault(key, default_value)
        # 为GUI配置创建父目录 (config/)
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"确保GUI配置目录 '{config_path.parent}' 存在。")
        except Exception as e:
            logger.error(f"为GUI配置创建目录 '{config_path.parent}' 失败: {e}")
            return False
    else:
        # 对于非GUI配置 (bot, lpmm等)
        # 仅当父目录 (例如 mmc_path/config/) 已存在时才保存
        if not config_path.parent.is_dir():
            logger.warning(
                f"父目录 '{config_path.parent}' (用于 '{config_type}' 配置) "
                f"不存在。文件将不会被保存。"
            )
            return False
        # 对于非GUI类型，我们不会在此处添加默认键，假设调用者已处理

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            tomlkit.dump(config_data, f)
        
        if not config_path.exists(): # 验证文件是否成功写入
            logger.error(f"配置文件 '{config_path}' 保存后似乎不存在。")
            return False
            
        logger.info(f"'{config_type}' 配置成功保存到 '{config_path}'")
        return True
    except Exception as e:
        logger.error(f"保存 '{config_type}' 配置到 '{config_path}' 时发生错误: {e}")
        import traceback
        traceback.print_exc()
    return False
