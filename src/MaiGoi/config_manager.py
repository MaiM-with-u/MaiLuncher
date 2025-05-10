import toml
from loguru import logger
import tomlkit
from pathlib import Path
import os
from typing import Dict, Any, Optional, List, Tuple, Union
import logging
from datetime import datetime
import shutil


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

# 定义可能的配置类型
CONFIG_TYPES = {
    "bot": "bot_config.toml",  # 机器人核心配置
    "lpmm": "lpmm_config.toml",  # LPMM配置 
    "gui": "gui_config.toml",   # GUI启动器配置
}

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


def get_config_path(config_type: str, base_dir: Optional[Union[str, Path]] = None) -> Path:
    """获取配置文件路径"""
    # 验证配置类型
    if config_type not in CONFIG_TYPES:
        raise ValueError(f"无效的配置类型: {config_type}. 可用类型: {', '.join(CONFIG_TYPES.keys())}")
    
    filename = CONFIG_TYPES[config_type]
    
    # 如果提供了基础目录，使用它
    if base_dir:
        base_path = Path(base_dir) if isinstance(base_dir, str) else base_dir
        config_path = base_path / "config" / filename
        # 确保config目录存在
        config_dir = base_path / "config"
        if not config_dir.exists():
            try:
                config_dir.mkdir(exist_ok=True, parents=True)
                logger.info(f"已创建配置目录: {config_dir}")
            except Exception as e:
                logger.error(f"创建配置目录失败: {e}")
    else:
        # 寻找bot.py并使用其所在目录作为基础目录
        try:
            # 如果我们不在MMC目录中，可能需要更复杂的搜索逻辑
            # 简单起见，先尝试使用当前目录
            base_path = Path.cwd()
            # 将来可以添加搜索逻辑
            config_path = base_path / "config" / filename
        except Exception as e:
            logger.error(f"无法确定配置路径: {e}")
            config_path = Path("./config") / filename
    
    logger.debug(f"配置路径 ({config_type}): {config_path}")
    return config_path


def load_config(config_type: str, base_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """加载指定类型的配置文件，返回TOML字典"""
    config_path = get_config_path(config_type, base_dir)
    logger.debug(f"尝试加载配置: {config_path}")
    
    # 检查文件是否存在
    if not config_path.exists():
        logger.warning(f"配置文件不存在: {config_path}")
        # 返回空配置而不是引发错误，以便应用程序可以继续
        return {}
    
    # 尝试多种编码方式读取文件
    encodings_to_try = ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'latin-1']
    for encoding in encodings_to_try:
        try:
            with open(config_path, "r", encoding=encoding) as f:
                config_content = f.read()
                
            # 尝试解析TOML内容
            try:
                config_data = tomlkit.parse(config_content)
                logger.info(f"成功加载配置: {config_path} (使用编码: {encoding})")
                return config_data
            except Exception as parse_error:
                logger.warning(f"解析配置文件失败 ({encoding}): {parse_error}")
                continue
                
        except Exception as read_error:
            logger.warning(f"读取配置文件失败 ({encoding}): {read_error}")
            continue
    
    # 如果所有编码都失败
    logger.error(f"尝试所有编码后无法加载配置文件: {config_path}")
    return {}


def save_config(config_data: Dict[str, Any], config_type: str, 
               base_dir: Optional[Union[str, Path]] = None, 
               backup: bool = True) -> bool:
    """保存配置到文件，可选择创建备份，返回是否成功"""
    config_path = get_config_path(config_type, base_dir)
    logger.debug(f"尝试保存配置: {config_path}")
    
    # 创建配置目录（如果不存在）
    config_path.parent.mkdir(exist_ok=True, parents=True)
    
    # 备份现有文件（如果存在且启用了备份）
    if backup and config_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup_path = config_path.with_name(f"{config_path.stem}_{timestamp}.bak")
        try:
            shutil.copy2(config_path, backup_path)
            logger.info(f"已创建配置备份: {backup_path}")
        except Exception as e:
            logger.warning(f"创建配置备份失败: {e}")
    
    # 保存新配置
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            tomlkit.dump(config_data, f)
        logger.info(f"已成功保存配置: {config_path}")
        return True
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        return False
