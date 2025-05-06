import toml

# Use tomlkit for dumping to preserve comments/formatting if needed,
# but stick to `toml` for loading unless specific features are required.
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


def get_config_path(config_type: str = "gui", base_dir: Optional[Path] = None) -> Optional[Path]:
    """Gets the full path to the specified config file type relative to a base directory."""
    global LAST_USED_CONFIG_PATHS
    
    filename = CONFIG_FILES.get(config_type)
    if not filename:
        print(f"[Config] Error: Unknown config type '{config_type}'")
        return None

    # --- 改进的 Base Directory 处理 --- #
    if base_dir is None:
        print(f"[Config] 警告: 未提供 base_dir 参数，尝试使用默认逻辑...")
        # 尝试使用相对于当前脚本的默认位置
        try:
            base_dir = Path(__file__).parent.parent.parent  # 默认为项目根目录
            print(f"[Config] 使用默认的 base_dir: {base_dir}")
        except Exception as e:
            print(f"[Config] 无法确定默认的 base_dir: {e}")
            return None
    elif not isinstance(base_dir, Path):
        # 尝试将非 Path 对象转换为 Path
        try:
            base_dir = Path(base_dir)
            print(f"[Config] 已转换 base_dir 为 Path 对象: {base_dir}")
        except Exception as e:
            print(f"[Config] 无法将 base_dir 转换为 Path 对象: {e}")
            return None

    # 确保 base_dir 是绝对路径
    try:
        if not base_dir.is_absolute():
            print(f"[Config] base_dir '{base_dir}' 不是绝对路径，尝试解析...")
            base_dir = base_dir.resolve()
            print(f"[Config] 已解析 base_dir 为: {base_dir}")
    except Exception as e:
        print(f"[Config] 解析 base_dir 时出错: {e}")
        # 继续使用原始 base_dir

    try:
        # 构建完整的配置文件路径
        config_path = base_dir / CONFIG_DIR / filename
        print(f"[Config] 计算出的配置路径: {config_path} (目录存在: {config_path.parent.exists()})")
        
        # 记录使用的配置路径
        LAST_USED_CONFIG_PATHS[config_type] = str(config_path)
        
        # 确保配置目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if not config_path.parent.exists():
            print(f"[Config] 警告：配置目录 {config_path.parent} 创建失败或不存在")
        
        return config_path
    except Exception as e:
        print(f"[Config] 构建配置路径时出错: {e}")
        return None


def load_config(config_type: str = "gui", base_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Loads the configuration from the specified TOML file type, relative to base_dir."""
    config_path = get_config_path(config_type, base_dir=base_dir)
    if not config_path:
        print(f"[Config] Could not determine config path for type '{config_type}' with base_dir '{base_dir}'.")
        # Optionally, could try get_config_path(config_type) without base_dir as a fallback
        return {} # Return empty dict if path is invalid

    print(f"[Config] Loading {config_type} config from: {config_path}")
    default_config_to_use = DEFAULT_GUI_CONFIG if config_type == "gui" else {}

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                # Use standard toml for loading, it's generally more robust
                config_data = toml.load(f)
                print(f"[Config] {config_type} config loaded successfully.")
                # Ensure all default keys exist for GUI config
                if config_type == "gui":
                    updated = False
                    for key, default_value in default_config_to_use.items():
                        if key not in config_data:
                            print(f"[Config] Key '{key}' not found in gui_config.toml, adding default: '{default_value}'")
                            config_data[key] = default_value
                            updated = True
                    # If we added missing keys, save the file back
                    # if updated:
                    #     print("[Config] Saving updated config with default keys.")
                    #     save_config(config_data, config_type="gui") # Avoid infinite loop if save fails
                return config_data
        else:
            print(f"[Config] {config_type} config file not found at '{config_path}', creating with defaults.")
            # Save default config - *** Crucially, pass base_dir here ***
            save_config(default_config_to_use.copy(), config_type=config_type, base_dir=base_dir)
            return default_config_to_use.copy()  # Return a copy
    except FileNotFoundError:
        print(f"[Config] {config_type} config file not found at '{config_path}' (FileNotFoundError), creating with defaults.")
        # Attempt to save default - *** Crucially, pass base_dir here ***
        save_config(default_config_to_use.copy(), config_type=config_type, base_dir=base_dir)
        return default_config_to_use.copy()
    except toml.TomlDecodeError as e:
        print(f"[Config] Error decoding {config_type} TOML file at '{config_path}': {e}. Using default.")
        # Decide whether to return default or empty on decode error
        default_config_to_use = DEFAULT_GUI_CONFIG if config_type == "gui" else {}
        return default_config_to_use.copy()
    except Exception as e:
        print(f"[Config] An unexpected error occurred loading {config_type} config: {e}.")
        import traceback

        traceback.print_exc()
        # Return a fresh copy of defaults on error
        return default_config_to_use.copy()


def save_config(config_data: Dict[str, Any], config_type: str = "gui", base_dir: Optional[Path] = None) -> bool:
    """Saves the configuration dictionary to the specified TOML file type, relative to base_dir."""
    config_path = get_config_path(config_type, base_dir=base_dir)
    if not config_path:
        print(f"[Config Save] Could not determine config path for type '{config_type}' with base_dir '{base_dir}'. Cannot save.")
        return False # Cannot save if path is invalid

    print(f"[Config] Saving {config_type} config to: {config_path}")
    
    # 打印要保存的适配器列表（如果存在）
    if config_type == "gui" and "adapters" in config_data:
        print(f"[Config] 即将保存的适配器列表: {config_data['adapters']}")

    # Ensure default keys exist before saving (important for GUI config)
    if config_type == "gui":
        default_config_to_use = DEFAULT_GUI_CONFIG
        for key, default_value in default_config_to_use.items():
            if key not in config_data:
                print(f"[Config Save] Adding missing default key '{key}': '{default_value}' before saving.")
                config_data[key] = default_value

    try:
        # 确保路径存在
        if not config_path.parent.exists():
            print(f"[Config] 警告：配置目录 {config_path.parent} 不存在，尝试创建...")
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
        with open(config_path, "w", encoding="utf-8") as f:
            # Use tomlkit.dump if preserving format/comments is important
            # Otherwise, stick to toml.dump for simplicity
            tomlkit.dump(config_data, f)  # Using tomlkit here
        
        # 验证文件是否成功写入
        if not config_path.exists():
            print(f"[Config] 警告：配置文件 {config_path} 似乎未成功写入")
            return False
            
        print(f"[Config] {config_type} config saved successfully to {config_path}")
        return True
    except IOError as e:
        print(f"[Config] Error writing {config_type} config file (IOError): {e}")
    except Exception as e:
        print(f"[Config] An unexpected error occurred saving {config_type} config: {e}")
        import traceback

        traceback.print_exc()
    return False
