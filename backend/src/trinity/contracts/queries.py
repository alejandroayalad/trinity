"""Closed policy messages without database or storage authority."""

from dataclasses import asdict, dataclass, field
import hashlib
import json


@dataclass(frozen=True)
class OutputColumn:
    """Preserve each public label and direct-source unit by position."""
    name: str
    unit: str | None


@dataclass(frozen=True)
class ValidatedQuery:
    """Bind the original input to a deterministic, versioned policy result."""
    original_sql: str = field(repr=False)
    dataset: str
    operation: str = field(repr=False)
    columns: tuple[OutputColumn, ...]
    policy_version: int = 1

    def to_bytes(self) -> bytes:
        """Encode the bounded internal message, never a public response."""
        return json.dumps(asdict(self), ensure_ascii=True, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()

    @property
    def digest(self) -> str:
        """Bind every policy field without authorizing a file location."""
        return hashlib.sha256(self.to_bytes()).hexdigest()

    @classmethod
    def from_bytes(cls, data: bytes) -> "ValidatedQuery":
        """Reject noncanonical, oversized or extended internal messages."""
        try:
            if len(data) > 256 * 1024:
                raise ValueError
            body = json.loads(data)
            if set(body) != {"original_sql", "dataset", "operation", "columns", "policy_version"}:
                raise ValueError
            if (type(body["policy_version"]) is not int or body["policy_version"] != 1
                    or any(type(body[k]) is not str for k in ("original_sql", "dataset", "operation"))
                    or type(body["columns"]) is not list or not 1 <= len(body["columns"]) <= 128):
                raise ValueError
            columns = []
            for c in body["columns"]:
                if (set(c) != {"name", "unit"} or type(c["name"]) is not str
                        or not 1 <= len(c["name"]) <= 128 or c["unit"] not in (None, "MW", "percent")):
                    raise ValueError
                columns.append(OutputColumn(**c))
            body["columns"] = tuple(columns)
            result = cls(**body)
            if result.to_bytes() != data:
                raise ValueError
            return result
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError("Invalid policy message.") from None
