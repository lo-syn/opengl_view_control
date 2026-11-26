import json5
import re
from pathlib import Path
from typing import Any
from dataclasses import dataclass

# This file is heavily inspired by the parse used in https://github.com/jimcortez/pyvvisf/blob/main/src/pyvvisf/parser.py
# Modified to fit with this application, but credit to jimcortez

@dataclass
class ISFInput:
    """ISF shader input."""

    name: str | None = None
    label: str | None = None
    type: str | None = None
    default: Any = None
    min: Any = None
    max: Any = None

class ISFMetaData:
    """ISF shader metadata."""

    name: str | None = None
    description: str | None = None
    author: str | None = None
    version: str | None = None
    license: str | None = None
    homepage: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    # ISF-specific fields
    inputs: Any = None
    passes: Any = None
    imports: dict[str, Any] | None = None
    # Render settings
    width: int | None = None
    height: int | None = None
    aspect_ratio: float | None = None
    # Shader info
    vertex_shader: str | None = None
    fragment_shader: str | None = None

class ISFHandler:
    def __init__(self):
        self.json_pattern = re.compile(r"/\*\s*\{([\s\S]*?)\}\s*\*/")
        self.content = ""
        self.inputs = []
        self.description = ""
        self.credit = ""
        self.isfvsn = ""

    def parse_file(self, file_path: str) -> tuple[bool, str|None, ISFMetaData|None]:
        """Parse an ISF shader file and return GLSL code and metadata."""
        """Return a tuple indicating if the file is an ISF shader, the GLSL content, and the metadata."""
        content = Path(file_path).read_text(encoding="utf-8")

        # Extract JSON metadata blocks
        json_blocks = self.json_pattern.findall(content)

        if not json_blocks:
            is_isf = False
            return is_isf, None, ISFMetaData()

        # Parse the first JSON block (ISF uses the first one).
        json_content = "{" + json_blocks[0] + "}"
        try:
            metadata_dict = json5.loads(json_content)
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Failed to parse ISF JSON metadata: {e}"
            ) from e

        # Remove JSON blocks from GLSL content
        glsl_content = self.json_pattern.sub("", content)

        metadata = ISFMetaData()
        metadata.name = metadata_dict.get("NAME")
        metadata.description = metadata_dict.get("DESCRIPTION")
        metadata.author = metadata_dict.get("AUTHOR", metadata_dict.get("CREDIT"))
        metadata.version = metadata_dict.get("VERSION")
        metadata.license = metadata_dict.get("LICENSE")
        metadata.homepage = metadata_dict.get("HOMEPAGE")
        categories = metadata_dict.get("CATEGORIES")
        metadata.category = categories[0] if categories else None
        metadata.tags = metadata_dict.get("TAGS")
        metadata.inputs = metadata_dict.get("INPUTS")
        metadata.passes = metadata_dict.get("PASSES")
        metadata.imports = metadata_dict.get("IMPORTS")
        metadata.width = metadata_dict.get("WIDTH")
        metadata.height = metadata_dict.get("HEIGHT")
        metadata.aspect_ratio = metadata_dict.get("ASPECT_RATIO")
        metadata.fragment_shader = glsl_content

        self.content = content
        self.inputs = metadata.inputs or []
        self.description = metadata.description or ""
        self.credit = metadata_dict.get("CREDIT", "")
        self.isfvsn = metadata_dict.get("ISFVSN", "")

        return True, glsl_content, metadata

    def parse_input(self, metadata: ISFMetaData) -> dict[str, ISFInput]:
        """Parse an individual input from the ISF metadata."""
        if not metadata.inputs:
            return {}

        processed_inputs = {}
        inputs: list[dict[str, Any]] = getattr(metadata, "inputs", None)
        for i in inputs:
            # Prioritize using the LABEL as the key for processed inputs, fallback to NAME if LABEL is not available
            name = i.get("NAME")
            label = i.get("LABEL")
            isf_input = ISFInput(name=i.get("NAME"), label=i.get("LABEL"), type=i.get("TYPE"), default=i.get("DEFAULT"), min=i.get("MIN"), max=i.get("MAX"))
            if label:
                processed_inputs[label]  = isf_input
            elif name:
                processed_inputs[name] = isf_input
            else:
                raise ValueError("Input must have either a LABEL or NAME.")

        return processed_inputs