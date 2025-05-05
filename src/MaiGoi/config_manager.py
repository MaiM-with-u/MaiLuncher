import toml

# Use tomlkit for dumping to preserve comments/formatting if needed,
# but stick to `toml` for loading unless specific features are required.
import tomlkit
from pathlib import Path
from typing import Dict, Any, Optional

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


def get_config_path(config_type: str = "gui", base_dir: Optional[Path] = None) -> Optional[Path]:
    """Gets the full path to the specified config file type relative to a base directory."""
    filename = CONFIG_FILES.get(config_type)
    if not filename:
        print(f"[Config] Error: Unknown config type '{config_type}'")
        return None

    # Determine the base directory relative to this file
    # Assumes config_manager.py is in src/MaiGoi/
    try:
        # Use provided base_dir if available, otherwise default to project root relative to this file
        if base_dir is None:
            print("[Config] Warning: base_dir not provided to get_config_path, attempting to default relative to script.")
            # Default logic: Assume project root is two levels up from this file's parent
            # This might be less reliable if the structure changes.
            script_dir = Path(__file__).parent.parent.parent  # Project Root (MaiBot-Core/)
        else:
            script_dir = base_dir # Use the provided base directory

        config_path = script_dir / CONFIG_DIR / filename
        return config_path
    except Exception as e:
        print(f"[Config] Error determining config path for type '{config_type}': {e}")
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
            print(f"[Config] {config_type} config file not found, creating with defaults.")
            # Save default config
            save_config(default_config_to_use.copy(), config_type=config_type)
            return default_config_to_use.copy()  # Return a copy
    except FileNotFoundError:
        print(f"[Config] {config_type} config file not found (FileNotFoundError), creating with defaults.")
        save_config(default_config_to_use.copy(), config_type=config_type)  # Attempt to save default
        return default_config_to_use.copy()
    except toml.TomlDecodeError as e:
        print(f"[Config] Error decoding {config_type} TOML file: {e}. Using default.")
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

    # Ensure default keys exist before saving (important for GUI config)
    if config_type == "gui":
        default_config_to_use = DEFAULT_GUI_CONFIG
        for key, default_value in default_config_to_use.items():
            if key not in config_data:
                print(f"[Config Save] Adding missing default key '{key}': '{default_value}' before saving.")
                config_data[key] = default_value

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)  # Ensure directory exists
        with open(config_path, "w", encoding="utf-8") as f:
            # Use tomlkit.dump if preserving format/comments is important
            # Otherwise, stick to toml.dump for simplicity
            tomlkit.dump(config_data, f)  # Using tomlkit here
        print(f"[Config] {config_type} config saved successfully.")
        return True
    except IOError as e:
        print(f"[Config] Error writing {config_type} config file (IOError): {e}")
    except Exception as e:
        print(f"[Config] An unexpected error occurred saving {config_type} config: {e}")
        import traceback

        traceback.print_exc()
    return False
