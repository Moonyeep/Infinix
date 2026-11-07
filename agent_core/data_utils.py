"""Data manipulation utilities for the Infinix agent."""
from __future__ import annotations

import csv
import io
import json
from typing import Any


def parse_json(text: str) -> dict[str, Any] | list[Any]:
    """Parse JSON string with error handling.
    
    Args:
        text: JSON string to parse
    
    Returns:
        Parsed JSON object (dict or list)
    
    Raises:
        ValueError: If JSON is invalid
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {str(e)}") from e


def format_json(data: Any, indent: int = 2) -> str:
    """Format data as pretty-printed JSON.
    
    Args:
        data: Data to format
        indent: Number of spaces for indentation
    
    Returns:
        Formatted JSON string
    """
    return json.dumps(data, indent=indent, ensure_ascii=False, default=str)


def parse_csv(text: str, delimiter: str = ",") -> list[dict[str, str]]:
    """Parse CSV text into list of dictionaries.
    
    Args:
        text: CSV text to parse
        delimiter: Column delimiter (default: comma)
    
    Returns:
        List of row dictionaries keyed by header
    """
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [dict(row) for row in reader]


def format_csv(data: list[dict[str, Any]], delimiter: str = ",") -> str:
    """Format list of dictionaries as CSV.
    
    Args:
        data: List of row dictionaries
        delimiter: Column delimiter (default: comma)
    
    Returns:
        CSV formatted string with headers
    """
    if not data:
        return ""
    
    output = io.StringIO()
    fieldnames = list(data[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=delimiter)
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


def merge_dicts(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries.
    
    Args:
        base: Base dictionary
        override: Dictionary with values to override/merge
    
    Returns:
        New merged dictionary
    """
    result = base.copy()
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten a nested dictionary.
    
    Args:
        d: Dictionary to flatten
        parent_key: Prefix for keys
        sep: Separator between levels
    
    Returns:
        Flattened dictionary with dot-separated keys
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)
