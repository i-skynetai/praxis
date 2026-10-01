"""The dict-of-types schema validator: ``{field: "str" | "int" | "float" | "bool" | "list"}``.

This is the validator the original seam shipped with, lifted behind the
``SchemaValidator`` port so that Pydantic or JSON Schema validators can sit beside it
later without the router knowing. A host's schema crosses this boundary as a
description, never as a host type.
"""

from __future__ import annotations

from collections.abc import Mapping

_TYPES: dict[str, type | tuple[type, ...]] = {
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
    "list": list,
    "dict": dict,
}


class DictOfTypesValidator:
    name = "dict-of-types"

    def validate(self, schema: Mapping[str, str], output: object) -> tuple[bool, str]:
        if not isinstance(output, Mapping):
            return False, f"expected an object, got {type(output).__name__}"
        for key, want in schema.items():
            if key not in output:
                return False, f"missing field {key!r}"
            expected = _TYPES.get(want)
            if expected is None:
                continue
            value = output[key]
            # bool is an int in Python; an "int" field must not accept True.
            if want in ("int", "float") and isinstance(value, bool):
                return False, f"field {key!r} should be {want}, got bool"
            if not isinstance(value, expected):
                return False, f"field {key!r} should be {want}, got {type(value).__name__}"
        extra = set(output) - set(schema)
        if extra:
            return False, f"unexpected fields: {sorted(str(k) for k in extra)}"
        return True, ""
