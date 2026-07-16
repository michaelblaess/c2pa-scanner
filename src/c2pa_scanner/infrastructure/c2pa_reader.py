"""C2PA-Leser: Adapter um die c2pa-Lib (implementiert das C2paReader-Protocol)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class C2paLibReader:
    """Liest C2PA-Manifeste ueber die offizielle c2pa-Lib."""

    def read(self, path: Path) -> tuple[bool, str | None]:
        """Gibt (has_c2pa, digital_source_type) zurueck. Kein Manifest -> (False, None)."""
        from c2pa import Reader

        reader = Reader.try_create(str(path))
        if reader is None:
            return (False, None)
        try:
            data = json.loads(reader.json())
        finally:
            reader.close()
        return (True, _find_digital_source_type(data))


def _find_digital_source_type(obj: Any) -> str | None:
    """Sucht rekursiv den ersten 'digitalSourceType'-Wert im Manifest-JSON."""
    if isinstance(obj, dict):
        value = obj.get("digitalSourceType")
        if isinstance(value, str) and value:
            return value
        for child in obj.values():
            found = _find_digital_source_type(child)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_digital_source_type(item)
            if found is not None:
                return found
    return None
