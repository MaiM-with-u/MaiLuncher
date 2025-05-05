import flet as ft
from pathlib import Path
from typing import List, Tuple, Optional
import time
import threading

# --- .env File Handling Logic ---


def load_env_data(env_path: Path) -> List[Tuple[str, str]]:
    """Loads key-value pairs from a .env file, skipping comments and empty lines."""
    variables = []
    if not env_path.exists():
        print(f"[Env Editor] .env file not found at {env_path}")
        return variables

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        # Basic handling for quotes (remove if present at ends)
                        if len(value) >= 2 and value.startswith(("'", '"')) and value.endswith(("'", '"')):
                            value = value[1:-1]
                        variables.append((key, value))
                    # else: Handle lines without '='? Maybe ignore them.

    except Exception as e:
        print(f"[Env Editor] Error loading .env file {env_path}: {e}")

    return variables


def save_env_data(env_path: Path, variables: List[Tuple[str, str]], silent: bool = False):
    """Saves key-value pairs back to the .env file, overwriting existing content."""
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            for key, value in variables:
                # Basic quoting if value contains spaces or special chars?
                # For simplicity, just write key=value for now.
                # Advanced quoting logic can be added if needed.
                f.write(f"{key}={value}\n")
        if not silent:
            print(f"[Env Editor] Successfully saved data to {env_path}")
        return True # Indicate success
    except Exception as e:
        print(f"[Env Editor] Error saving .env file {env_path}: {e}")
        # Optionally raise or show error to user
        return False # Indicate failure


# --- Flet UI Component ---


# Inherit directly from ft.Column instead of ft.UserControl
class EnvEditor(ft.Column):
    """A Flet Column containing controls for editing .env file variables with auto-save."""

    def __init__(self, app_state, debounce_interval: float = 1.5):
        # Initialize the Column base class
        # Pass Column properties like spacing, scroll, expand here
        super().__init__(spacing=5, scroll=ft.ScrollMode.ADAPTIVE, expand=True)

        self.app_state = app_state
        self.env_path = Path(self.app_state.script_dir) / ".env"
        self.variables = load_env_data(self.env_path)
        self.debounce_interval = debounce_interval
        self.save_timer: Optional[threading.Timer] = None

        # UI Controls - Define them as instance attributes
        self.variable_rows_column = ft.Column([], spacing=5, scroll=ft.ScrollMode.ADAPTIVE)
        self.add_key_field = ft.TextField(label="New Key", width=150)
        self.add_value_field = ft.TextField(label="New Value", expand=True)
        # self.save_button = ft.ElevatedButton("Save Changes", icon=ft.icons.SAVE, on_click=self._save_changes) # Removed
        self.status_text = ft.Text("", size=12, italic=True) # For showing save status/errors

        # --- Build the UI directly within __init__ ---
        self._populate_rows()  # Populate rows initially

        add_row = ft.Row(
            [
                self.add_key_field,
                self.add_value_field,
                ft.IconButton(
                    icon=ft.icons.ADD_CIRCLE_OUTLINE,
                    tooltip="Add Variable (auto-saves)",
                    on_click=self._add_variable_row_interactive,
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
        )

        # Add controls directly to self (the Column)
        self.controls.extend(
            [
                ft.Text(".env File Editor", style=ft.TextThemeStyle.HEADLINE_SMALL),
                ft.Text(f"Editing: {self.env_path.name} (in {self.env_path.parent})"),
                ft.Divider(),
                self.variable_rows_column,  # Add the column that holds the variable rows
                ft.Divider(),
                ft.Text("Add New Variable:", style=ft.TextThemeStyle.LABEL_LARGE),
                add_row,
                ft.Divider(),
                ft.Row([self.status_text], alignment=ft.MainAxisAlignment.END), # Status text only
            ]
        )
        # No need to return anything from __init__

    def _populate_rows(self):
        """Clears and refills the variable rows column based on self.variables."""
        self.variable_rows_column.controls.clear()
        for index, (key, value) in enumerate(self.variables):
            self.variable_rows_column.controls.append(self._create_variable_row(index, key, value))
        # No need to update here, usually called during init or after add/delete

    def _create_variable_row(self, index: int, key: str, value: str) -> ft.Row:
        """Creates a Row control for a single key-value pair."""
        key_field = ft.TextField(value=key, expand=2, data=index)
        value_field = ft.TextField(value=value, expand=5, data=index)

        # Add on_change to trigger debounced save
        key_field.on_change = self._handle_change
        value_field.on_change = self._handle_change

        return ft.Row(
            [
                key_field,
                value_field,
                ft.IconButton(
                    icon=ft.icons.DELETE_OUTLINE,
                    tooltip="Delete Variable (auto-saves)",
                    data=index,  # Store index to know which one to delete
                    on_click=self._delete_variable_row,
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
            key=str(index),  # Assign a key for potential targeted updates
        )

    def _handle_change(self, e):
        """Called when any key or value TextField changes."""
        # Value is implicitly updated in the TextField
        # Trigger the debounced save which will read all current values
        self._trigger_debounced_save()

    def _add_variable_row_interactive(self, e):
        """Adds a variable row based on the 'Add New' fields and updates the UI."""
        new_key = self.add_key_field.value.strip()
        new_value = self.add_value_field.value.strip()

        if not new_key:
            # Access page via self.page if the control is mounted
            if self.page:
                self.page.show_snack_bar(ft.SnackBar(ft.Text("Key cannot be empty."), open=True))
            return

        # Check if key already exists? For now, allow duplicates, save will handle last one.

        # Add to internal list
        self.variables.append((new_key, new_value))

        # Add UI row
        new_index = len(self.variables) - 1
        self.variable_rows_column.controls.append(self._create_variable_row(new_index, new_key, new_value))

        # Clear add fields
        self.add_key_field.value = ""
        self.add_value_field.value = ""

        self.update()  # Update this Column
        # If page exists, update page too (might be redundant if Column update cascades)
        # if self.page: self.page.update()
        self._trigger_debounced_save() # Trigger save after adding

    def _delete_variable_row(self, e):
        """Deletes a variable row from the UI and the internal list."""
        index_to_delete = e.control.data

        if 0 <= index_to_delete < len(self.variables):
            # Find the row control to remove
            row_to_remove = None
            for control in self.variable_rows_column.controls:
                # Check the data attribute of the delete button inside the row
                if (
                    isinstance(control, ft.Row)
                    and len(control.controls) > 2
                    and isinstance(control.controls[2], ft.IconButton)
                    and control.controls[2].data == index_to_delete
                ):
                    row_to_remove = control
                    break

            # Remove from internal list *first*
            if index_to_delete < len(self.variables):  # Double check index after finding row
                del self.variables[index_to_delete]
            else:
                print(f"[Env Editor] Error: Index {index_to_delete} out of bounds after finding row.")
                return

            # Remove from UI column if found
            if row_to_remove:
                self.variable_rows_column.controls.remove(row_to_remove)

            # Need to re-index remaining rows' data attributes
            self._reindex_rows()

            self.update()  # Update this Column
            # if self.page: self.page.update()
            self._trigger_debounced_save() # Trigger save after deleting
        else:
            print(f"[Env Editor] Error: Invalid index to delete: {index_to_delete}")

    def _reindex_rows(self):
        """Updates the data attribute (index) of controls in each row after deletion."""
        for i, row in enumerate(self.variable_rows_column.controls):
            if isinstance(row, ft.Row) and len(row.controls) > 2:
                # Update index on key field, value field, and delete button
                if isinstance(row.controls[0], ft.TextField):
                    row.controls[0].data = i
                if isinstance(row.controls[1], ft.TextField):
                    row.controls[1].data = i
                if isinstance(row.controls[2], ft.IconButton):
                    row.controls[2].data = i

    def _trigger_debounced_save(self):
        """Triggers the save action after a debounce interval."""
        if self.save_timer:
            self.save_timer.cancel()

        def save_action():
            print(f"[Env Editor Debounce] Triggering save at {time.time():.2f}")
            self._save_changes(silent=True)
            self.save_timer = None

        self.save_timer = threading.Timer(self.debounce_interval, save_action)
        self.save_timer.start()
        print(f"[Env Editor Debounce] Save scheduled in {self.debounce_interval}s at {time.time():.2f}")
        # Update status immediately to show pending save
        self.status_text.value = "Saving..."
        self.status_text.color = ft.colors.ON_SURFACE_VARIANT # Neutral color
        try:
             self.update() # Update status text visibility
        except Exception:
            pass # Ignore if update fails before mount

    def _save_changes(self, e=None, silent: bool = False):
        """Collects data from UI rows and saves to the .env file."""
        updated_variables = []
        has_error = False
        keys = set()

        for row_index, row in enumerate(self.variable_rows_column.controls):
            if isinstance(row, ft.Row) and len(row.controls) >= 2:
                key_field = row.controls[0]
                value_field = row.controls[1]
                if isinstance(key_field, ft.TextField) and isinstance(value_field, ft.TextField):
                    key = key_field.value.strip()
                    value = value_field.value  # Keep original spacing/quotes for value for now
                    if not key:
                        has_error = True
                        # Use row_index which reflects the current visual order
                        self.status_text.value = f"Error: Row {row_index + 1} has an empty key."
                        self.status_text.color = ft.colors.RED
                        break  # Stop processing on first error
                    if key in keys:
                        print(f"[Env Editor] Warning: Duplicate key '{key}' found. Last occurrence will be saved.")
                        # Or show error? Let's allow for now, last wins on save.
                    keys.add(key)
                    updated_variables.append((key, value))
                else:
                    has_error = True
                    self.status_text.value = "Error: Invalid row structure found."
                    self.status_text.color = ft.colors.RED
                    break
            else:  # Handle cases where row might not be what's expected
                print(f"[Env Editor] Warning: Skipping unexpected control type in variable column: {type(row)}")

        if not has_error:
            save_successful = save_env_data(self.env_path, updated_variables, silent=silent)
            if save_successful:
                self.variables = updated_variables  # Update internal state only on successful save
                self.status_text.value = f"Saved successfully at {time.strftime('%H:%M:%S')}"
                self.status_text.color = ft.colors.GREEN_700
            else:
                self.status_text.value = "Error saving changes!"
                self.status_text.color = ft.colors.RED
        else:
             # Error message already set in the loop
             pass

        # Update UI to show status
        try:
            self.update()
        except Exception:
             pass # Ignore if control not mounted


# --- Function to create the main view containing the editor ---
# This can be called from ui_settings_view.py
def create_env_editor_page_content(page: ft.Page, app_state) -> ft.Control:
    """Creates the EnvEditor control."""
    # EnvEditor is now the Column itself
    editor = EnvEditor(app_state)
    return editor
