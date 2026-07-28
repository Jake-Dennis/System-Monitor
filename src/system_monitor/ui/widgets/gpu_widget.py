"""GPU card. Shows one row per adapter with util, VRAM, power, fan."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from .. import styles
from ._base import _Card
from ._timeline import Timeline


_VENDOR_LABEL = {
    "nvidia": "NVIDIA",
    "amd": "AMD",
    "intel": "Intel",
    "unknown": "GPU",
}


class _GpuRow(QWidget):
    """One GPU adapter: util bar + VRAM bar + power/fan."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # Row 1: util bar
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)

        self._name = QLabel("--")
        self._name.setObjectName("CardTitle")
        self._name.setFixedWidth(200)
        self._name.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self._util_bar = QProgressBar()
        self._util_bar.setRange(0, 100)
        self._util_bar.setValue(0)
        self._util_bar.setTextVisible(False)
        self._util_bar.setFixedHeight(6)

        self._util_pct = QLabel("--")
        self._util_pct.setObjectName("ValueSmall")
        self._util_pct.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._util_pct.setFixedWidth(50)

        self._source = QLabel("")
        self._source.setObjectName("Caption")
        self._source.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        row1.addWidget(self._name)
        row1.addWidget(self._util_bar, 1)
        row1.addWidget(self._util_pct)
        row1.addWidget(self._source)
        root.addLayout(row1)

        # Row 2: VRAM bar
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)

        self._vram_label = QLabel("VRAM")
        self._vram_label.setObjectName("Caption")
        self._vram_label.setFixedWidth(130)
        self._vram_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self._vram_bar = QProgressBar()
        self._vram_bar.setRange(0, 100)
        self._vram_bar.setValue(0)
        self._vram_bar.setTextVisible(False)
        self._vram_bar.setFixedHeight(6)

        self._vram_pct = QLabel("--")
        self._vram_pct.setObjectName("ValueSmall")
        self._vram_pct.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._vram_pct.setFixedWidth(50)

        row2.addWidget(self._vram_label)
        row2.addWidget(self._vram_bar, 1)
        row2.addWidget(self._vram_pct)
        root.addLayout(row2)

        # Row 3: details (power, fan, VRAM size text)
        self._details = QLabel("")
        self._details.setObjectName("Secondary")
        root.addWidget(self._details)

        # Row 4: util timeline
        self._timeline = Timeline()
        self._timeline.set_color(styles.ACCENT)
        root.addWidget(self._timeline)

    def set_gpu(self, gpu: dict[str, Any]) -> None:
        vendor_raw = gpu.get("vendor", "unknown")
        vendor = _VENDOR_LABEL.get(vendor_raw, vendor_raw.upper())
        name = (gpu.get("name") or "GPU").strip()
        # Show full model name. If different from vendor, prefix it.
        if vendor_raw != "unknown" and not name.upper().startswith(vendor.upper()):
            display = f"{vendor} · {name}"
        else:
            display = name
        self._name.setText(display)

        # Util bar
        util = float(gpu.get("util_percent", 0.0))
        color = styles.color_for_percent(util)
        self._util_pct.setText(f"{util:.0f}%")
        self._util_bar.setValue(int(max(0.0, min(100.0, util))))
        self._util_bar.setStyleSheet(
            "QProgressBar { background: rgba(0,0,0,80); border: none; "
            "height: 6px; border-radius: 3px; }"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )
        source = gpu.get("source", "")
        self._source.setText("")

        # VRAM bar
        mem_used = float(gpu.get("mem_used_mb", 0.0))
        mem_total = float(gpu.get("mem_total_mb", 0.0))
        if mem_total > 0:
            mem_pct = float(gpu.get("mem_percent", 0.0))
            self._vram_pct.setText(f"{mem_pct:.0f}%")
            self._vram_bar.setValue(int(max(0.0, min(100.0, mem_pct))))
            vram_color = styles.color_for_percent(mem_pct)
            self._vram_bar.setStyleSheet(
                "QProgressBar { background: rgba(0,0,0,80); border: none; "
                "height: 6px; border-radius: 3px; }"
                f"QProgressBar::chunk {{ background: {vram_color}; border-radius: 3px; }}"
            )
        else:
            self._vram_pct.setText("--")
            self._vram_bar.setValue(0)

        # Detail line: power · fan · VRAM size
        parts: list[str] = []
        if mem_total > 0:
            parts.append(f"{mem_used:.0f}/{mem_total:.0f} MB")
        elif mem_total == 0 and mem_used == 0:
            parts.append("VRAM n/a")
        power = gpu.get("power_w")
        if power is not None:
            parts.append(f"{float(power):.0f} W")
        fan = gpu.get("fan_percent")
        if fan is not None:
            parts.append(f"fan {float(fan):.0f}%")
        self._details.setText("   ·   ".join(parts) if parts else "")

        # Timeline
        self._timeline.set_color(color)
        self._timeline.add_point(util)


class GpuCard(_Card):
    def __init__(self, parent=None) -> None:
        super().__init__("GPU", parent)
        layout = self.layout()  # type: ignore[arg-type]

        # Remove the default big-value label, bar, and secondary text so we
        # can replace them with a list of per-GPU rows.
        for i in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is None:
                continue
            if w.objectName() in ("Value", "Secondary"):
                if isinstance(w, QProgressBar) or w.objectName() == "Value":
                    layout.removeWidget(w)
                    w.hide()
                    w.deleteLater()
                elif w.objectName() == "Secondary":
                    # Keep a footer label; remove the default bar.
                    layout.removeWidget(w)
                    w.hide()
                    w.deleteLater()

        # Container for GPU rows (inserted right after the title).
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(10)
        layout.insertWidget(1, self._rows_host)

        self._footer = QLabel("")
        self._footer.setObjectName("Secondary")
        self._footer.hide()
        layout.addWidget(self._footer)

        self._rows: list[_GpuRow] = []
        self.hidden_gpus: set[str] = set()  # indices/names to hide
        self.visible_gpu_list: list[str] = []  # last known GPU names for menu

    def update(self, snapshot: dict[str, Any]) -> None:
        gpus = snapshot.get("gpus", []) or []
        cpu_power = snapshot.get("cpu", {}).get("power_w")

        # Track visible GPU names for the settings menu
        self.visible_gpu_list = [
            g.get("name", g.get("vendor", f"GPU {i}") or f"GPU {i}")
            for i, g in enumerate(gpus)
        ]

        # Filter out hidden GPUs
        hidden = self.hidden_gpus
        gpus = [
            g for i, g in enumerate(gpus)
            if g.get("name", f"GPU {i}") not in hidden
        ]

        # Reconcile row count with GPU count.
        while len(self._rows) < len(gpus):
            row = _GpuRow()
            self._rows.append(row)
            self._rows_layout.addWidget(row)
        while len(self._rows) > len(gpus):
            row = self._rows.pop()
            self._rows_layout.removeWidget(row)
            row.hide()
            row.deleteLater()

        if not gpus:
            # Show placeholder.
            if not self._rows:
                ph = QLabel("No GPU detected. NVIDIA works out of the box;\n"
                            "AMD/Intel need LibreHardwareMonitor running (see README).")
                ph.setObjectName("Secondary")
                ph.setWordWrap(True)
                self._rows_layout.addWidget(ph)
            self._footer.setText("")
        else:
            # Remove any leftover placeholder.
            for i in range(self._rows_layout.count() - 1, -1, -1):
                item = self._rows_layout.itemAt(i)
                w = item.widget() if item is not None else None
                if (
                    w is not None
                    and isinstance(w, QLabel)
                    and w.objectName() == "Secondary"
                    and w not in self._rows
                    and w is not self._footer
                ):
                    self._rows_layout.removeWidget(w)
                    w.hide()
                    w.deleteLater()

            for row, gpu in zip(self._rows, gpus):
                row.set_gpu(gpu)
                row.show()

            # Footer: adapter count + source breakdown + combined power.
            sources: dict[str, int] = {}
            for g in gpus:
                s = g.get("source", "unknown")
                sources[s] = sources.get(s, 0) + 1
            footer_parts = [f"{len(gpus)} adapter" + ("s" if len(gpus) != 1 else "")]
            srcs = [f"{count} {src}" for src, count in sources.items()]
            footer_parts.append(" / ".join(srcs))

            gpu_power = sum(
                float(g.get("power_w", 0.0) or 0.0) for g in gpus
            )
            if cpu_power is not None and gpu_power > 0:
                total = cpu_power + gpu_power
                footer_parts.append(
                    f"CPU {cpu_power:.0f} + GPU {gpu_power:.0f} = {total:.0f} W"
                )
            elif gpu_power > 0:
                footer_parts.append(f"{gpu_power:.0f} W")

            self._footer.setText("  ·  ".join(footer_parts))
