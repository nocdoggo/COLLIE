"""Alert bank: templates with hidden canonical specs, conditions, and content controls."""

from __future__ import annotations

from collie.data.alerts.bank import (
    AlertTemplate,
    RenderedAlert,
    assert_no_text_leakage,
    load_alert_bank,
    render_alert,
    scan_text_for_leakage,
)

__all__ = [
    "AlertTemplate",
    "RenderedAlert",
    "assert_no_text_leakage",
    "load_alert_bank",
    "render_alert",
    "scan_text_for_leakage",
]
