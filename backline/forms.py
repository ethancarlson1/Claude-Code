"""Declarative form fields shared by the create/edit pages."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from . import util


class Field:
    def __init__(
        self,
        name,
        label,
        type="text",
        required=False,
        choices=None,
        section=None,
        help=None,
        placeholder=None,
        wide=False,
        default=None,
    ):
        self.name = name
        self.label = label
        self.type = type
        self.required = required
        self.choices = choices
        self.section = section
        self.help = help
        self.placeholder = placeholder
        self.wide = wide or type == "textarea"
        self.default = default

    def options(self):
        """Select options as (value, label) pairs; callables are resolved lazily."""
        choices = self.choices() if callable(self.choices) else (self.choices or [])
        return [c if isinstance(c, tuple) else (c, c) for c in choices]


def parse(fields, form):
    """Validate submitted form data. Returns (data, errors)."""
    data, errors = {}, {}
    for f in fields:
        if f.type == "checkbox":
            data[f.name] = 1 if form.get(f.name) else 0
            continue
        raw = (form.get(f.name) or "").strip()
        if not raw:
            if f.required:
                errors[f.name] = f"{f.label} is required."
            data[f.name] = None
            continue
        try:
            data[f.name] = _convert(f, raw)
        except ValueError as exc:
            errors[f.name] = str(exc) or f"{f.label} is invalid."
    return data, errors


def _convert(f, raw):
    if f.type in ("money", "number"):
        try:
            value = Decimal(raw.replace(",", "").replace("$", ""))
        except InvalidOperation:
            raise ValueError(f"{f.label} must be a number.") from None
        return float(util.round_money(value)) if f.type == "money" else float(value)
    if f.type == "int":
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(f"{f.label} must be a whole number.") from None
        if value < 0:
            raise ValueError(f"{f.label} can't be negative.")
        return value
    if f.type == "date":
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
        except ValueError:
            raise ValueError(f"{f.label} must be a date (YYYY-MM-DD).") from None
    if f.type == "time":
        try:
            return datetime.strptime(raw[:5], "%H:%M").strftime("%H:%M")
        except ValueError:
            raise ValueError(f"{f.label} must be a time (HH:MM).") from None
    if f.type in ("select", "fk"):
        allowed = {str(v) for v, _ in f.options()}
        if raw not in allowed:
            raise ValueError(f"Choose a valid {f.label.lower()}.")
        return int(raw) if f.type == "fk" else raw
    return raw


def sections(fields):
    """Group fields by their section, preserving order."""
    grouped = []
    for f in fields:
        if not grouped or grouped[-1][0] != f.section:
            grouped.append((f.section, []))
        grouped[-1][1].append(f)
    return grouped
