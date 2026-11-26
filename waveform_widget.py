from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from audio_engine import format_time
from themes import MODERN_WAVEFORM_PALETTE, WaveformPalette


class WaveformWidget(QWidget):
    """Widget interativo para visualizar a forma de onda e ajustar In/Out/Playhead."""

    rangeChanged = Signal(float, float)
    seekRequested = Signal(float)
    zoomChanged = Signal(float)

    RULER_HEIGHT = 24
    HANDLE_HIT_PX = 10
    MIN_SELECTION_SEC = 0.05

    def __init__(
        self,
        parent: QWidget | None = None,
        palette: WaveformPalette | None = None,
    ) -> None:
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._palette: WaveformPalette = palette or MODERN_WAVEFORM_PALETTE
        self._peaks: np.ndarray | None = None
        self._duration: float = 0.0
        self._start_sec: float = 0.0
        self._end_sec: float = 0.0
        self._playhead_sec: float = 0.0

        self._zoom: float = 1.0
        self._view_start: float = 0.0  # início visível em segundos

        self._drag_mode: str | None = None  # "start", "end", "playhead", "pan"
        self._pan_anchor_x: float = 0.0
        self._pan_anchor_view_start: float = 0.0
        self._hover_target: str | None = None

    def set_palette(self, palette: WaveformPalette) -> None:
        self._palette = palette
        self.update()

    def view_state(self) -> tuple[float, float]:
        return self._zoom, self._view_start

    def restore_view_state(self, zoom: float, view_start: float) -> None:
        if self._duration <= 0:
            return
        self._zoom = max(1.0, min(float(zoom), 60.0))
        span = self._visible_span()
        self._view_start = max(0.0, min(float(view_start), max(0.0, self._duration - span)))
        self.zoomChanged.emit(self._zoom)
        self.update()

    def set_audio(self, peaks: np.ndarray, duration: float) -> None:
        self._peaks = peaks
        self._duration = max(0.0, float(duration))
        self._start_sec = 0.0
        self._end_sec = self._duration
        self._playhead_sec = 0.0
        self._zoom = 1.0
        self._view_start = 0.0
        self.zoomChanged.emit(self._zoom)
        self.update()

    def clear_audio(self) -> None:
        self._peaks = None
        self._duration = 0.0
        self._start_sec = 0.0
        self._end_sec = 0.0
        self._playhead_sec = 0.0
        self._zoom = 1.0
        self._view_start = 0.0
        self.update()

    def set_range(self, start_sec: float, end_sec: float) -> None:
        if self._duration <= 0:
            return
        start_sec = max(0.0, min(start_sec, self._duration - self.MIN_SELECTION_SEC))
        end_sec = max(start_sec + self.MIN_SELECTION_SEC, min(end_sec, self._duration))
        self._start_sec = start_sec
        self._end_sec = end_sec
        self.update()

    def set_playhead(self, pos_sec: float) -> None:
        self._playhead_sec = max(0.0, min(pos_sec, self._duration))
        if self._zoom > 1.0 and self._drag_mode is None:
            view_span = self._visible_span()
            if self._playhead_sec < self._view_start:
                self._view_start = max(0.0, self._playhead_sec - view_span * 0.1)
            elif self._playhead_sec > self._view_start + view_span:
                self._view_start = min(
                    max(0.0, self._duration - view_span),
                    self._playhead_sec - view_span * 0.1,
                )
        self.update()

    def zoom_factor(self) -> float:
        return self._zoom

    def reset_zoom(self) -> None:
        self._zoom = 1.0
        self._view_start = 0.0
        self.zoomChanged.emit(self._zoom)
        self.update()

    def set_zoom(self, new_zoom: float, anchor_sec: float | None = None) -> None:
        if self._duration <= 0:
            return
        new_zoom = max(1.0, min(new_zoom, 60.0))
        old_span = self._visible_span()
        if anchor_sec is None:
            anchor_sec = self._view_start + old_span * 0.5
        rel = (anchor_sec - self._view_start) / old_span if old_span > 0 else 0.5

        self._zoom = new_zoom
        new_span = self._visible_span()
        self._view_start = max(
            0.0,
            min(anchor_sec - rel * new_span, max(0.0, self._duration - new_span)),
        )
        self.zoomChanged.emit(self._zoom)
        self.update()

    def _visible_span(self) -> float:
        if self._duration <= 0:
            return 1.0
        return self._duration / self._zoom

    def _time_to_x(self, sec: float) -> float:
        span = self._visible_span()
        if span <= 0:
            return 0.0
        return ((sec - self._view_start) / span) * max(1, self.width())

    def _x_to_time(self, x: float) -> float:
        span = self._visible_span()
        w = max(1, self.width())
        t = self._view_start + (x / w) * span
        return max(0.0, min(t, self._duration))

    def _hit_test(self, x: float) -> str:
        if self._duration <= 0:
            return "none"
        sx = self._time_to_x(self._start_sec)
        ex = self._time_to_x(self._end_sec)
        dist_s = abs(x - sx)
        dist_e = abs(x - ex)
        if dist_s <= self.HANDLE_HIT_PX and dist_e <= self.HANDLE_HIT_PX:
            return "start" if dist_s <= dist_e else "end"
        if dist_s <= self.HANDLE_HIT_PX:
            return "start"
        if dist_e <= self.HANDLE_HIT_PX:
            return "end"
        return "playhead"

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._duration <= 0:
            return
        x = event.position().x()
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self._drag_mode = "pan"
            self._pan_anchor_x = x
            self._pan_anchor_view_start = self._view_start
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            target = self._hit_test(x)
            self._drag_mode = target
            self._apply_drag(x)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._duration <= 0:
            return
        x = event.position().x()
        if self._drag_mode == "pan":
            dx = x - self._pan_anchor_x
            span = self._visible_span()
            dt = (dx / max(1, self.width())) * span
            self._view_start = max(
                0.0,
                min(self._pan_anchor_view_start - dt, max(0.0, self._duration - span)),
            )
            self.update()
            return

        if self._drag_mode is not None:
            self._apply_drag(x)
            return

        target = self._hit_test(x)
        self._hover_target = target
        if target in ("start", "end"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.IBeamCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode is not None:
            self._drag_mode = None
            target = self._hit_test(event.position().x())
            if target in ("start", "end"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self._duration <= 0:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.angleDelta().x()
        if delta == 0:
            return

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            span = self._visible_span()
            step = span * 0.15 * (-1 if delta > 0 else 1)
            self._view_start = max(
                0.0, min(self._view_start + step, max(0.0, self._duration - span))
            )
            self.update()
            return

        factor = 1.25 if delta > 0 else 0.8
        anchor_sec = self._x_to_time(event.position().x())
        self.set_zoom(self._zoom * factor, anchor_sec=anchor_sec)

    def _apply_drag(self, x: float) -> None:
        t = self._x_to_time(x)
        if self._drag_mode == "start":
            new_start = min(t, self._end_sec - self.MIN_SELECTION_SEC)
            new_start = max(0.0, new_start)
            if abs(new_start - self._start_sec) > 1e-6:
                self._start_sec = new_start
                self.rangeChanged.emit(self._start_sec, self._end_sec)
                self.update()
        elif self._drag_mode == "end":
            new_end = max(t, self._start_sec + self.MIN_SELECTION_SEC)
            new_end = min(self._duration, new_end)
            if abs(new_end - self._end_sec) > 1e-6:
                self._end_sec = new_end
                self.rangeChanged.emit(self._start_sec, self._end_sec)
                self.update()
        elif self._drag_mode == "playhead":
            self._playhead_sec = t
            self.seekRequested.emit(self._playhead_sec)
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        pal = self._palette
        w = self.width()
        h = self.height()
        wave_top = self.RULER_HEIGHT
        wave_h = max(10, h - wave_top)
        mid_y = wave_top + wave_h / 2.0

        # Fundo geral
        painter.fillRect(0, 0, w, h, QColor(pal.bg))
        painter.fillRect(0, 0, w, self.RULER_HEIGHT, QColor(pal.ruler_bg))

        if self._peaks is None or self._duration <= 0:
            if pal.classic_style:
                self._draw_classic_grid(painter, w, wave_top, wave_h, mid_y)
            painter.setPen(QColor(pal.empty_text))
            font = QFont("Segoe UI", 10 if pal.classic_style else 11)
            painter.setFont(font)
            painter.drawText(
                QRectF(0, wave_top, w, wave_h),
                Qt.AlignmentFlag.AlignCenter,
                "Arraste um arquivo de áudio aqui ou clique em 'Abrir Áudio'",
            )
            painter.setPen(QPen(QColor(pal.ruler_border), 1))
            painter.drawLine(0, self.RULER_HEIGHT, w, self.RULER_HEIGHT)
            painter.setPen(QPen(QColor(pal.border), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(0, 0, w - 1, h - 1)
            return

        # Grade sutil de osciloscópio no tema clássico
        if pal.classic_style:
            self._draw_classic_grid(painter, w, wave_top, wave_h, mid_y)

        # Régua de tempo
        self._draw_ruler(painter, w)

        # Fundo da região selecionada
        sx = self._time_to_x(self._start_sec)
        ex = self._time_to_x(self._end_sec)
        sel_left = max(0.0, sx)
        sel_right = min(float(w), ex)
        if sel_right > sel_left:
            painter.fillRect(
                QRectF(sel_left, wave_top, sel_right - sel_left, wave_h),
                QColor(*pal.selection_fill),
            )

        # Linha central
        painter.setPen(QPen(QColor(pal.center_line), 1))
        painter.drawLine(0, int(mid_y), w, int(mid_y))

        # Forma de onda
        self._draw_waveform(painter, w, wave_top, wave_h, mid_y, sx, ex)

        # Máscara escura fora do intervalo
        if sx > 0:
            painter.fillRect(
                QRectF(0, wave_top, min(float(w), sx), wave_h),
                QColor(*pal.dim_overlay),
            )
        if ex < w:
            left_dim = max(0.0, ex)
            painter.fillRect(
                QRectF(left_dim, wave_top, w - left_dim, wave_h),
                QColor(*pal.dim_overlay),
            )

        # Marcadores In / Out
        self._draw_handle(
            painter,
            sx,
            wave_top,
            h,
            QColor(pal.handle_in),
            "IN",
            align_right=False,
            active=(self._drag_mode == "start"),
            time_val=self._start_sec,
        )
        self._draw_handle(
            painter,
            ex,
            wave_top,
            h,
            QColor(pal.handle_out),
            "OUT",
            align_right=True,
            active=(self._drag_mode == "end"),
            time_val=self._end_sec,
        )

        # Playhead
        px = self._time_to_x(self._playhead_sec)
        if -2 <= px <= w + 2:
            painter.setPen(QPen(QColor(pal.playhead), 1.8))
            painter.drawLine(QPointF(px, wave_top), QPointF(px, h))
            tri = QPolygonF(
                [
                    QPointF(px - 6, wave_top),
                    QPointF(px + 6, wave_top),
                    QPointF(px, wave_top + 8),
                ]
            )
            painter.setBrush(QColor(pal.playhead))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon(tri)

        # Borda do widget
        painter.setPen(QPen(QColor(pal.border), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, w - 1, h - 1)

    def _draw_classic_grid(
        self,
        painter: QPainter,
        w: int,
        wave_top: int,
        wave_h: int,
        mid_y: float,
    ) -> None:
        painter.setPen(QPen(QColor(self._palette.grid_line), 1, Qt.PenStyle.DotLine))
        quarter = wave_h * 0.25
        for y in (mid_y - quarter, mid_y + quarter):
            painter.drawLine(0, int(y), w, int(y))
        step_x = max(60, w // 12)
        for gx in range(step_x, w, step_x):
            painter.drawLine(gx, wave_top, gx, wave_top + wave_h)

    def _draw_ruler(self, painter: QPainter, w: int) -> None:
        pal = self._palette
        span = self._visible_span()
        candidates = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
        target_ticks = max(4, w // 110)
        step = candidates[-1]
        for c in candidates:
            if span / c <= target_ticks:
                step = c
                break

        first_tick = int(self._view_start // step) * step
        painter.setFont(QFont("Consolas", 8))
        t = first_tick
        while t <= self._view_start + span + step * 0.1:
            x = self._time_to_x(t)
            if 0 <= x <= w:
                painter.setPen(QPen(QColor(pal.ruler_tick), 1))
                painter.drawLine(QPointF(x, self.RULER_HEIGHT - 7), QPointF(x, self.RULER_HEIGHT))
                painter.setPen(QColor(pal.ruler_text))
                label = format_time(t, include_ms=(step < 1.0))
                painter.drawText(QPointF(x + 4, self.RULER_HEIGHT - 8), label)
            t += step

        painter.setPen(QPen(QColor(pal.ruler_border), 1))
        painter.drawLine(0, self.RULER_HEIGHT, w, self.RULER_HEIGHT)

    def _draw_waveform(
        self,
        painter: QPainter,
        w: int,
        wave_top: int,
        wave_h: int,
        mid_y: float,
        sx: float,
        ex: float,
    ) -> None:
        pal = self._palette
        peaks = self._peaks
        assert peaks is not None
        n = len(peaks)
        span = self._visible_span()
        half_amp = (wave_h * 0.44)

        idx_start_f = (self._view_start / self._duration) * n
        idx_end_f = ((self._view_start + span) / self._duration) * n

        pen_in = QPen(QColor(pal.wave_in), 1)
        pen_out = QPen(QColor(pal.wave_out), 1)

        for x in range(w):
            b0 = int(idx_start_f + (x / max(1, w)) * (idx_end_f - idx_start_f))
            b1 = int(idx_start_f + ((x + 1) / max(1, w)) * (idx_end_f - idx_start_f))
            b0 = max(0, min(b0, n - 1))
            b1 = max(b0 + 1, min(b1, n))

            seg = peaks[b0:b1]
            vmin = float(seg[:, 0].min())
            vmax = float(seg[:, 1].max())

            y_top = mid_y - vmax * half_amp
            y_bot = mid_y - vmin * half_amp
            if y_bot - y_top < 1.0:
                y_top = mid_y - 0.5
                y_bot = mid_y + 0.5

            painter.setPen(pen_in if sx <= x <= ex else pen_out)
            painter.drawLine(QPointF(x, y_top), QPointF(x, y_bot))

    def _draw_handle(
        self,
        painter: QPainter,
        x: float,
        wave_top: int,
        h: int,
        color: QColor,
        label: str,
        align_right: bool,
        active: bool,
        time_val: float,
    ) -> None:
        if x < -20 or x > self.width() + 20:
            return
        pal = self._palette
        line_w = 2.5 if active else 2.0
        painter.setPen(QPen(color, line_w))
        painter.drawLine(QPointF(x, wave_top), QPointF(x, h))

        tab_w = 32
        tab_h = 18
        tab_x = x - tab_w if align_right else x
        tab_x = max(0.0, min(tab_x, self.width() - tab_w))

        painter.setBrush(color)
        if pal.classic_style:
            painter.setPen(QPen(QColor("#0b0d0f"), 1))
            painter.drawRect(QRectF(tab_x, wave_top + 1, tab_w, tab_h))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.addRoundedRect(QRectF(tab_x, wave_top + 2, tab_w, tab_h), 4, 4)
            painter.drawPath(path)

        painter.setPen(QColor(pal.handle_text))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(
            QRectF(tab_x, wave_top + (1 if pal.classic_style else 2), tab_w, tab_h),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )

        if active:
            pill_text = format_time(time_val, include_ms=True)
            pill_w = 78
            pill_h = 20
            pill_x = max(4.0, min(x - pill_w / 2.0, self.width() - pill_w - 4.0))
            pill_y = h - pill_h - 6
            painter.setBrush(QColor(pal.pill_bg))
            painter.setPen(QPen(color, 1))
            if pal.classic_style:
                painter.drawRect(QRectF(pill_x, pill_y, pill_w, pill_h))
            else:
                painter.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 4, 4)
            painter.setPen(QColor(pal.pill_text))
            painter.setFont(QFont("Consolas", 8))
            painter.drawText(
                QRectF(pill_x, pill_y, pill_w, pill_h),
                Qt.AlignmentFlag.AlignCenter,
                pill_text,
            )
