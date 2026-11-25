from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidget, QListWidgetItem


_DIRECTORY_ROLE = Qt.ItemDataRole.UserRole + 1
_DEPTH_ROLE = Qt.ItemDataRole.UserRole + 2

DEFAULT_BROWSER_PATH = r"C:\Users\Laurence\Documents\Video Art\opengl_view\bin\data"

class BrowserHandler:
    def __init__(self, directory: Path | str):
        self.directory = Path(directory) if not isinstance(directory, Path) else directory
        self._expanded_directories: set[Path] = set()

    def populate(self, list_widget: QListWidget, browser_filter: list[str] | None = None) -> None:
        self._expanded_directories.clear()
        list_widget.clear()
        entries = sorted(self.directory.iterdir(), key=lambda entry: entry.name.casefold())

        for entry in entries:
            if entry.is_dir():
                list_widget.addItem(self._create_item(entry))
            elif browser_filter is None or entry.suffix in browser_filter:
                list_widget.addItem(self._create_item(entry))

    def toggle_directory(self, list_widget: QListWidget, item: QListWidgetItem, browser_filter: list[str] | None = None) -> None:
        if item is None or not item.data(_DIRECTORY_ROLE):
            return

        directory = Path(item.data(Qt.ItemDataRole.UserRole))
        if directory in self._expanded_directories:
            self._collapse_directory(list_widget, directory)
            return

        entries = sorted(directory.iterdir(), key=lambda entry: entry.name.casefold())
        insertion_row = list_widget.row(item) + 1
        depth = item.data(_DEPTH_ROLE) + 1
        # Insert entries for the directory, respecting the browser filter and depth
        # Directories are allowed regardless of the browser filter
        inserted_count = 0
        for entry in entries:
            if browser_filter is None or entry.is_dir() or entry.suffix in browser_filter:
                list_widget.insertItem(
                    insertion_row + inserted_count, self._create_item(entry, depth=depth)
                )
                inserted_count += 1
        self._expanded_directories.add(directory)

    def _collapse_directory(self, list_widget: QListWidget, directory: Path) -> None:
        for row in range(list_widget.count() - 1, -1, -1):
            item = list_widget.item(row)
            entry_path = Path(item.data(Qt.ItemDataRole.UserRole))
            if entry_path != directory and directory in entry_path.parents:
                list_widget.takeItem(row)

        self._expanded_directories = {
            expanded
            for expanded in self._expanded_directories
            if expanded != directory and directory not in expanded.parents
        }

    @staticmethod
    def _create_item(entry: Path, depth: int = 0) -> QListWidgetItem:
        item = QListWidgetItem(f"    " * depth + entry.name)
        item.setData(Qt.ItemDataRole.UserRole, str(entry))
        item.setData(_DIRECTORY_ROLE, entry.is_dir())
        item.setData(_DEPTH_ROLE, depth)
        return item