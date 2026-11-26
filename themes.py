from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap, QPolygonF

THEME_MODERN = "modern"
THEME_CLASSIC = "classic"


@dataclass(frozen=True)
class WaveformPalette:
    bg: str
    ruler_bg: str
    ruler_tick: str
    ruler_text: str
    ruler_border: str
    empty_text: str
    center_line: str
    grid_line: str
    selection_fill: tuple[int, int, int, int]
    dim_overlay: tuple[int, int, int, int]
    wave_in: str
    wave_out: str
    handle_in: str
    handle_out: str
    handle_text: str
    playhead: str
    border: str
    pill_bg: str
    pill_text: str
    classic_style: bool = False


@dataclass(frozen=True)
class ThemeSpec:
    id: str
    name: str
    description: str
    stylesheet: str
    waveform_palette: WaveformPalette


MODERN_WAVEFORM_PALETTE = WaveformPalette(
    bg="#0f172a",
    ruler_bg="#111827",
    ruler_tick="#334155",
    ruler_text="#94a3b8",
    ruler_border="#1e293b",
    empty_text="#64748b",
    center_line="#1e293b",
    grid_line="#1e293b",
    selection_fill=(56, 189, 248, 28),
    dim_overlay=(2, 6, 23, 130),
    wave_in="#38bdf8",
    wave_out="#475569",
    handle_in="#22c55e",
    handle_out="#f59e0b",
    handle_text="#0f172a",
    playhead="#f43f5e",
    border="#1e293b",
    pill_bg="#020617",
    pill_text="#f8fafc",
    classic_style=False,
)


CLASSIC_WAVEFORM_PALETTE = WaveformPalette(
    bg="#0d1013",
    ruler_bg="#25282c",
    ruler_tick="#6d747d",
    ruler_text="#d6dce2",
    ruler_border="#495057",
    empty_text="#8a939e",
    center_line="#26382b",
    grid_line="#171d22",
    selection_fill=(46, 204, 113, 30),
    dim_overlay=(0, 0, 0, 145),
    wave_in="#35c96b",
    wave_out="#4b5561",
    handle_in="#4ade80",
    handle_out="#f59e0b",
    handle_text="#0b0d0f",
    playhead="#ff3b30",
    border="#3a3f46",
    pill_bg="#101418",
    pill_text="#e6edf3",
    classic_style=True,
)


DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0b1120;
    color: #e2e8f0;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: #0b1120;
    color: #cbd5e1;
    border-bottom: 1px solid #1e293b;
    padding: 2px 6px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #1e293b;
    color: #f8fafc;
}
QMenu {
    background-color: #111827;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 4px;
}
QMenu::item {
    padding: 6px 26px 6px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #1e293b;
    color: #38bdf8;
}
QMenu::item:disabled {
    color: #475569;
}
QMenu::separator {
    height: 1px;
    background: #1e293b;
    margin: 4px 8px;
}
QFrame#Card {
    background-color: #111827;
    border: 1px solid #1e293b;
    border-radius: 10px;
}
QLabel#TitleLabel {
    font-size: 16px;
    font-weight: 600;
    color: #f8fafc;
}
QLabel#MetaLabel {
    color: #94a3b8;
    font-size: 12px;
}
QLabel#BadgeLossless {
    background-color: rgba(34, 197, 94, 0.16);
    color: #4ade80;
    border: 1px solid rgba(34, 197, 94, 0.4);
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 12px;
}
QLabel#PlayheadLabel {
    font-family: "Consolas", monospace;
    color: #f8fafc;
    font-weight: 600;
}
QLabel#ZoomLabel {
    color: #94a3b8;
    min-width: 40px;
}
QLabel#InLabel {
    color: #4ade80;
    font-weight: 600;
}
QLabel#OutLabel {
    color: #fbbf24;
    font-weight: 600;
}
QLabel#DurationLabel {
    font-family: "Consolas", monospace;
    font-size: 17px;
    font-weight: 700;
    color: #38bdf8;
}
QLineEdit {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f8fafc;
    font-family: "Consolas", monospace;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #38bdf8;
}
QPushButton {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 7px 14px;
    color: #f1f5f9;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #273549;
    border-color: #475569;
}
QPushButton:pressed {
    background-color: #0f172a;
}
QPushButton:disabled {
    color: #64748b;
    background-color: #111827;
    border-color: #1e293b;
}
QPushButton#PrimaryButton {
    background-color: #0284c7;
    border: 1px solid #0ea5e9;
    color: #ffffff;
    font-weight: 600;
    padding: 9px 18px;
}
QPushButton#PrimaryButton:hover {
    background-color: #0ea5e9;
}
QPushButton#PrimaryButton:disabled {
    background-color: #1e293b;
    border-color: #334155;
    color: #64748b;
}
QPushButton#NudgeButton {
    padding: 5px 8px;
    font-size: 12px;
    min-width: 42px;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #1e293b;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #38bdf8;
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
QProgressBar {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #38bdf8;
    border-radius: 3px;
}
"""


CLASSIC_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #f0f0f0;
    color: #111111;
    font-family: "Segoe UI", "Tahoma", sans-serif;
    font-size: 12px;
}
QMenuBar {
    background-color: #f5f5f5;
    color: #111111;
    border-bottom: 1px solid #c6c6c6;
    padding: 1px 2px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 9px;
    border: 1px solid transparent;
}
QMenuBar::item:selected {
    background-color: #cce8ff;
    border: 1px solid #99d1ff;
    color: #000000;
}
QMenu {
    background-color: #f7f7f7;
    color: #111111;
    border: 1px solid #999999;
    padding: 2px;
}
QMenu::item {
    padding: 5px 28px 5px 24px;
    border: 1px solid transparent;
}
QMenu::item:selected {
    background-color: #cce8ff;
    border: 1px solid #99d1ff;
    color: #000000;
}
QMenu::item:disabled {
    color: #8c8c8c;
}
QMenu::separator {
    height: 1px;
    background: #d4d4d4;
    margin: 3px 6px;
}
QFrame#ClassicHeaderBar {
    background-color: #e9e9e9;
    border: 1px solid #c5c5c5;
}
QFrame#ClassicViewport {
    background-color: #0d1013;
    border-top: 1px solid #7a7a7a;
    border-left: 1px solid #7a7a7a;
    border-bottom: 1px solid #ffffff;
    border-right: 1px solid #ffffff;
}
QFrame#ClassicTransportBar {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #f6f6f6, stop:1 #e4e4e4);
    border: 1px solid #bdbdbd;
}
QFrame#ClassicDivider {
    background-color: #b8b8b8;
    max-width: 1px;
    min-width: 1px;
}
QGroupBox {
    background-color: #f0f0f0;
    border: 1px solid #bcbcbc;
    margin-top: 9px;
    padding-top: 6px;
    font-weight: 600;
    color: #222222;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    background-color: #f0f0f0;
}
QLabel#TitleLabel {
    font-size: 13px;
    font-weight: 600;
    color: #111111;
    background: transparent;
}
QLabel#MetaLabel {
    color: #3a3a3a;
    font-size: 11px;
    background: transparent;
}
QLabel#ClassicLcd {
    background-color: #14171a;
    color: #35d46b;
    border-top: 1px solid #666666;
    border-left: 1px solid #666666;
    border-bottom: 1px solid #ffffff;
    border-right: 1px solid #ffffff;
    padding: 3px 8px;
    font-family: "Consolas", monospace;
    font-size: 12px;
    font-weight: 700;
}
QLabel#ClassicDurationBox {
    background-color: #ffffff;
    color: #004e98;
    border-top: 1px solid #7a7a7a;
    border-left: 1px solid #7a7a7a;
    border-bottom: 1px solid #d8d8d8;
    border-right: 1px solid #d8d8d8;
    padding: 4px 10px;
    font-family: "Consolas", monospace;
    font-size: 14px;
    font-weight: 700;
}
QLabel#ClassicInTag {
    background-color: #1f8b4c;
    color: #ffffff;
    padding: 2px 5px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#ClassicOutTag {
    background-color: #c97208;
    color: #ffffff;
    padding: 2px 5px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#BadgeLossless {
    background-color: #eaf5ec;
    color: #1c6b32;
    border: 1px solid #8ec29b;
    padding: 2px 7px;
    font-weight: 600;
    font-size: 11px;
}
QLabel#ZoomLabel {
    color: #222222;
    background-color: #ffffff;
    border: 1px solid #adadad;
    padding: 2px 4px;
    min-width: 38px;
    font-family: "Consolas", monospace;
    font-size: 11px;
}
QLineEdit {
    background-color: #ffffff;
    border-top: 1px solid #7a7a7a;
    border-left: 1px solid #7a7a7a;
    border-bottom: 1px solid #c6c6c6;
    border-right: 1px solid #c6c6c6;
    border-radius: 0px;
    padding: 3px 6px;
    color: #111111;
    font-family: "Consolas", monospace;
    font-size: 12px;
}
QLineEdit:focus {
    border: 1px solid #0078d7;
}
QLineEdit:disabled {
    background-color: #e8e8e8;
    color: #777777;
}
QPushButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #f9f9f9, stop:1 #dfdfdf);
    border: 1px solid #adadad;
    border-radius: 2px;
    padding: 4px 10px;
    color: #111111;
    font-weight: 400;
}
QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #f2f9ff, stop:1 #d9ecff);
    border-color: #0078d7;
}
QPushButton:pressed {
    background-color: #cce4f7;
    border-color: #005499;
}
QPushButton:disabled {
    background-color: #e7e7e7;
    border-color: #c8c8c8;
    color: #8c8c8c;
}
QPushButton#PrimaryButton {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #f3f9ff, stop:1 #cfe6fc);
    border: 1px solid #0078d7;
    color: #003a6c;
    font-weight: 600;
    padding: 5px 14px;
}
QPushButton#PrimaryButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #e3f2ff, stop:1 #b8dcff);
    border-color: #005a9e;
}
QPushButton#PrimaryButton:pressed {
    background-color: #a9d3fa;
}
QPushButton#PrimaryButton:disabled {
    background-color: #e7e7e7;
    border-color: #c8c8c8;
    color: #8c8c8c;
}
QPushButton#ClassicToolButton {
    padding: 3px 7px;
    min-width: 26px;
    min-height: 22px;
    font-size: 12px;
}
QPushButton#NudgeButton {
    padding: 3px 6px;
    font-size: 11px;
    min-width: 36px;
}
QCheckBox {
    spacing: 5px;
    background: transparent;
    color: #111111;
}
QCheckBox:disabled {
    color: #8c8c8c;
}
QSlider::groove:horizontal {
    height: 4px;
    background: #ffffff;
    border-top: 1px solid #7a7a7a;
    border-left: 1px solid #7a7a7a;
    border-bottom: 1px solid #dcdcdc;
    border-right: 1px solid #dcdcdc;
}
QSlider::sub-page:horizontal {
    background: #0078d7;
    border: 1px solid #005a9e;
}
QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #ffffff, stop:1 #d6d6d6);
    border: 1px solid #707070;
    width: 10px;
    margin: -5px 0;
    border-radius: 1px;
}
QSlider::handle:horizontal:hover {
    background: #d9ecff;
    border-color: #0078d7;
}
QProgressBar {
    background-color: #ffffff;
    border-top: 1px solid #7a7a7a;
    border-left: 1px solid #7a7a7a;
    border-bottom: 1px solid #d4d4d4;
    border-right: 1px solid #d4d4d4;
    height: 12px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #06b025;
}
QStatusBar {
    background-color: #f0f0f0;
    color: #222222;
    border-top: 1px solid #c0c0c0;
}
QStatusBar::item {
    border: 1px solid #cfcfcf;
    border-radius: 0px;
}
QLabel#StatusCell {
    padding: 1px 8px;
    color: #222222;
    font-size: 11px;
    background: transparent;
}
QLabel#StatusTimeCell {
    padding: 1px 8px;
    color: #111111;
    font-family: "Consolas", monospace;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
}
"""


THEMES: dict[str, ThemeSpec] = {
    THEME_MODERN: ThemeSpec(
        id=THEME_MODERN,
        name="Moderno (Escuro)",
        description="Visual atual em modo escuro com cards arredondados",
        stylesheet=DARK_STYLESHEET,
        waveform_palette=MODERN_WAVEFORM_PALETTE,
    ),
    THEME_CLASSIC: ThemeSpec(
        id=THEME_CLASSIC,
        name="Clássico (VLC / MPC)",
        description="Interface clássica inspirada em players tradicionais de desktop",
        stylesheet=CLASSIC_STYLESHEET,
        waveform_palette=CLASSIC_WAVEFORM_PALETTE,
    ),
}


def get_theme(theme_id: str) -> ThemeSpec:
    return THEMES.get(theme_id, THEMES[THEME_MODERN])


def build_qt_palette(theme_id: str) -> QPalette:
    pal = QPalette()
    if theme_id == THEME_CLASSIC:
        pal.setColor(QPalette.ColorRole.Window, QColor("#f0f0f0"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#111111"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#f5f5f5"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#111111"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#e1e1e1"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#111111"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#0078d7"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffe1"))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#111111"))
    else:
        pal.setColor(QPalette.ColorRole.Window, QColor("#0b1120"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#e2e8f0"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#0f172a"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#111827"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#f8fafc"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#1e293b"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#f1f5f9"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#0284c7"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#111827"))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#f8fafc"))
    return pal


def _render_classic_glyph(name: str, color: QColor, size: int = 16) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)

    if name == "play":
        p.drawPolygon(QPolygonF([QPointF(4, 2.5), QPointF(13.5, 8), QPointF(4, 13.5)]))
    elif name == "pause":
        p.drawRect(QRectF(3.5, 3, 3.2, 10))
        p.drawRect(QRectF(9.3, 3, 3.2, 10))
    elif name == "stop":
        p.drawRect(QRectF(3.5, 3.5, 9, 9))
    elif name == "play_sel":
        p.drawRect(QRectF(2, 3, 1.8, 10))
        p.drawPolygon(QPolygonF([QPointF(5, 3), QPointF(11.5, 8), QPointF(5, 13)]))
        p.drawRect(QRectF(12.2, 3, 1.8, 10))
    elif name == "jump_in":
        p.drawRect(QRectF(2.5, 3, 2, 10))
        p.drawPolygon(QPolygonF([QPointF(13, 3), QPointF(5.5, 8), QPointF(13, 13)]))
    elif name == "jump_out":
        p.drawPolygon(QPolygonF([QPointF(3, 3), QPointF(10.5, 8), QPointF(3, 13)]))
        p.drawRect(QRectF(11.5, 3, 2, 10))
    elif name == "volume":
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(2, 6),
                    QPointF(5.2, 6),
                    QPointF(8.8, 3),
                    QPointF(8.8, 13),
                    QPointF(5.2, 10),
                    QPointF(2, 10),
                ]
            )
        )
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(8.5, 5, 3.5, 6), -50 * 16, 100 * 16)
        p.drawArc(QRectF(9.5, 3, 5, 10), -50 * 16, 100 * 16)
    elif name == "open":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color, 1.4))
        p.drawPolygon(
            QPolygonF(
                [
                    QPointF(2, 4),
                    QPointF(6.2, 4),
                    QPointF(7.6, 5.5),
                    QPointF(14, 5.5),
                    QPointF(14, 12.5),
                    QPointF(2, 12.5),
                ]
            )
        )
    elif name == "save":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color, 1.4))
        p.drawRect(QRectF(2.5, 2.5, 11, 11))
        p.drawRect(QRectF(5, 2.5, 6, 4))
        p.drawRect(QRectF(4.5, 8.8, 7, 4.7))

    p.end()
    return pm


def make_classic_icon(name: str) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_render_classic_glyph(name, QColor("#1f2328")), QIcon.Mode.Normal)
    icon.addPixmap(_render_classic_glyph(name, QColor("#9a9a9a")), QIcon.Mode.Disabled)
    return icon

