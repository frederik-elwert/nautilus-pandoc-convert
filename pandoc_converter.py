#!/usr/bin/env python3

import os
import re
import subprocess
from multiprocessing import Process
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

import yaml
from gi.repository import GObject, Nautilus


class PandocConverterExtension(GObject.GObject, Nautilus.MenuProvider):
    FORMAT_EXTENSIONS = {
        "docx": ".docx",
        "epub": ".epub",
        "html": ".html",
        "markdown": ".md",
        "odt": ".odt",
        "pdf": ".pdf",
        "pptx": ".pptx",
        "tei": ".xml",
        "latex": ".tex",
        "typst": ".typ",
        "revealjs": ".html",
    }

    def __init__(self):
        super().__init__()
        self.defaults_files = self._find_defaults_files()
        print("Initializing Nautilus Pandoc Converter")

    def _get_pandoc_data_dir(self) -> Optional[Path]:
        """Find the Pandoc data directory."""
        xdg_data_home = Path(os.getenv("XDG_DATA_HOME", "~/.local/share")).expanduser()
        possible_paths = [xdg_data_home / "pandoc", Path.home() / ".pandoc"]

        for path in possible_paths:
            if path.is_dir():
                return path
        return None

    def _find_defaults_files(self) -> Dict[str, Path]:
        """Find all defaults files in the Pandoc data directory."""
        defaults_files = {}
        data_dir = self._get_pandoc_data_dir()

        if not data_dir:
            return defaults_files

        defaults_dir = data_dir / "defaults"
        if not defaults_dir.is_dir():
            return defaults_files

        for filepath in defaults_dir.glob("*.yaml"):
            try:
                config = yaml.safe_load(filepath.read_text())
                # Check if the config specifies an output format
                output_format = config.get("to") or config.get("write")
                if output_format:
                    menu_name = filepath.stem
                    defaults_files[menu_name] = filepath
            except (yaml.YAMLError, IOError):
                continue

        return defaults_files

    @staticmethod
    def _run_conversion(input_path: str, defaults_file: str) -> None:
        """Static method to run the conversion in a separate process."""
        try:
            # Read the output format from the defaults file
            with open(defaults_file, "r") as f:
                config = yaml.safe_load(f)
                output_format = config.get("to") or config.get("write")

            if not output_format:
                return

            # Strip extensions and get output path
            base_format = re.split(r"[+-]", output_format)[0]
            extension = PandocConverterExtension.FORMAT_EXTENSIONS.get(
                base_format, f".{base_format}"
            )
            input_path_obj = Path(input_path)
            output_path = input_path_obj.with_suffix(extension)
            # Run pandoc
            subprocess.run(
                ["pandoc", "-d", defaults_file, input_path, "-o", str(output_path)],
                cwd=input_path_obj.parent,
                check=True,
            )

            # Send notification on completion
            subprocess.run(
                [
                    "notify-send",
                    "Pandoc Conversion Complete",
                    f"Converted {input_path_obj.name} to {output_path.name}",
                ]
            )

        except Exception as e:
            # Send notification on error
            subprocess.run(
                [
                    "notify-send",
                    "Pandoc Conversion Error",
                    f"Error converting {input_path_obj.name}: {str(e)}",
                ]
            )

    def _convert_file(self, input_path: Path, defaults_file: Path) -> None:
        """Start the conversion process in a separate process."""
        # Create and start the conversion process
        Process(
            target=self._run_conversion,
            args=(str(input_path), str(defaults_file)),
            daemon=True,
        ).start()

    def get_file_items(self, files: List[Nautilus.FileInfo]) -> List[Nautilus.MenuItem]:
        """Create menu items for Markdown files."""
        if len(files) != 1:
            return []

        file_info = files[0]
        file_path = Path(unquote(file_info.get_uri()[7:]))  # Remove 'file://' prefix

        # Check if this is a Markdown file
        if file_path.suffix.lower() not in [".md", ".markdown"]:
            return []

        # Create the main menu item
        convert_item = Nautilus.MenuItem(
            name="PandocConverter::Convert", label="Convert", tip="Convert using Pandoc"
        )

        # Create the submenu
        submenu = Nautilus.Menu()
        convert_item.set_submenu(submenu)

        # Add submenu items for each defaults file
        for menu_name, defaults_path in self.defaults_files.items():
            sub_item = Nautilus.MenuItem(
                name=f"PandocConverter::Convert::{menu_name}",
                label=menu_name,
                tip=f"Convert using {menu_name} defaults",
            )
            sub_item.connect(
                "activate",
                lambda w, path=file_path, df=defaults_path: self._convert_file(
                    path, df
                ),
            )
            submenu.append_item(sub_item)

        return [convert_item] if self.defaults_files else []

    def get_background_items(self, current_folder) -> List[Nautilus.MenuItem]:
        """Required by the interface, but we don't need background items."""
        return []
