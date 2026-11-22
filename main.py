from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from audio_engine import (
    SUPPORTED_EXTENSIONS,
    AudioInfo,
    TrimResult,
    extract_waveform_peaks,
    format_time,
    parse_time,
    probe_audio,
    trim_audio_lossless,
)
from waveform_widget import WaveformWidget


DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0b1120;
    color: #e2e8f0;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
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


class LoadAudioWorker(QThread):
    loaded = Signal(object, object)  # AudioInfo, np.ndarray
    failed = Signal(str)

    def __init__(self, file_path: Path) -> None:
        super().__init__()
        self.file_path = file_path

    def run(self) -> None:
        try:
            info = probe_audio(self.file_path)
            peaks = extract_waveform_peaks(self.file_path, num_bins=3000)
            self.loaded.emit(info, peaks)
        except Exception as exc:
            self.failed.emit(str(exc))


class TrimWorker(QThread):
    finished_ok = Signal(object)  # TrimResult
    failed = Signal(str)

    def __init__(
        self,
        input_path: Path,
        output_path: Path,
        start_sec: float,
        end_sec: float,
        audio_info: AudioInfo,
    ) -> None:
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.start_sec = start_sec
        self.end_sec = end_sec
        self.audio_info = audio_info

    def run(self) -> None:
        try:
            res = trim_audio_lossless(
                self.input_path,
                self.output_path,
                self.start_sec,
                self.end_sec,
                self.audio_info,
            )
            self.finished_ok.emit(res)
        except Exception as exc:
            self.failed.emit(str(exc))


class AudioTrimmerWindow(QMainWindow):
    def __init__(self, initial_file: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Cortador de Áudio Sem Perda (Qt + FFmpeg)")
        self.resize(980, 620)
        self.setAcceptDrops(True)

        self._audio_info: AudioInfo | None = None
        self._start_sec: float = 0.0
        self._end_sec: float = 0.0
        self._play_selection_only: bool = False
        self._load_worker: LoadAudioWorker | None = None
        self._trim_worker: TrimWorker | None = None
        self._last_output_path: Path | None = None

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.85)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_player_position_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

        self._build_ui()
        self._setup_shortcuts()
        self._update_controls_enabled(False)

        if initial_file and initial_file.exists():
            self.load_file(initial_file)

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(16, 16, 16, 14)
        main_layout.setSpacing(12)

        # --- Cabeçalho ---
        header_card = QFrame()
        header_card.setObjectName("Card")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(14, 12, 14, 12)

        self.btn_open = QPushButton("Abrir Áudio...")
        self.btn_open.clicked.connect(self._on_open_clicked)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self.lbl_title = QLabel("Nenhum arquivo carregado")
        self.lbl_title.setObjectName("TitleLabel")
        self.lbl_meta = QLabel("Arraste MP3, M4A, WAV, FLAC, OGG, OPUS ou clique em Abrir Áudio")
        self.lbl_meta.setObjectName("MetaLabel")
        info_col.addWidget(self.lbl_title)
        info_col.addWidget(self.lbl_meta)

        self.lbl_badge = QLabel("Stream Copy • Sem Perda")
        self.lbl_badge.setObjectName("BadgeLossless")

        header_layout.addWidget(self.btn_open)
        header_layout.addLayout(info_col, 1)
        header_layout.addWidget(self.lbl_badge)
        main_layout.addWidget(header_card)

        # --- Waveform Card ---
        wave_card = QFrame()
        wave_card.setObjectName("Card")
        wave_layout = QVBoxLayout(wave_card)
        wave_layout.setContentsMargins(12, 12, 12, 10)
        wave_layout.setSpacing(8)

        self.waveform = WaveformWidget()
        self.waveform.rangeChanged.connect(self._on_waveform_range_changed)
        self.waveform.seekRequested.connect(self._on_waveform_seek)
        self.waveform.zoomChanged.connect(self._on_zoom_changed)
        wave_layout.addWidget(self.waveform, 1)

        # Barra de transporte + zoom
        transport = QHBoxLayout()
        transport.setSpacing(8)

        self.btn_play = QPushButton("Tocar (Espaço)")
        self.btn_play.clicked.connect(self._toggle_play)

        self.btn_play_sel = QPushButton("Tocar Seleção")
        self.btn_play_sel.clicked.connect(self._play_selection)

        self.btn_stop = QPushButton("Parar")
        self.btn_stop.clicked.connect(self._stop_playback)

        self.chk_loop = QCheckBox("Loop")
        self.chk_loop.setToolTip("Repetir trecho selecionado continuamente")

        self.lbl_playhead = QLabel("00:00.000")
        self.lbl_playhead.setStyleSheet("font-family: Consolas; color: #f8fafc; font-weight: 600;")

        transport.addWidget(self.btn_play)
        transport.addWidget(self.btn_play_sel)
        transport.addWidget(self.btn_stop)
        transport.addWidget(self.chk_loop)
        transport.addSpacing(10)
        transport.addWidget(QLabel("Cursor:"))
        transport.addWidget(self.lbl_playhead)
        transport.addStretch(1)

        # Zoom
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setObjectName("NudgeButton")
        self.btn_zoom_out.clicked.connect(lambda: self.waveform.set_zoom(self.waveform.zoom_factor() * 0.7))

        self.lbl_zoom = QLabel("1.0x")
        self.lbl_zoom.setStyleSheet("color: #94a3b8; min-width: 40px;")
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setObjectName("NudgeButton")
        self.btn_zoom_in.clicked.connect(lambda: self.waveform.set_zoom(self.waveform.zoom_factor() * 1.4))

        self.btn_zoom_reset = QPushButton("Reset Zoom")
        self.btn_zoom_reset.clicked.connect(self.waveform.reset_zoom)

        transport.addWidget(QLabel("Zoom:"))
        transport.addWidget(self.btn_zoom_out)
        transport.addWidget(self.lbl_zoom)
        transport.addWidget(self.btn_zoom_in)
        transport.addWidget(self.btn_zoom_reset)

        # Volume
        transport.addSpacing(8)
        transport.addWidget(QLabel("Vol:"))
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(85)
        self.slider_vol.setFixedWidth(90)
        self.slider_vol.valueChanged.connect(lambda v: self._audio_output.setVolume(v / 100.0))
        transport.addWidget(self.slider_vol)

        wave_layout.addLayout(transport)
        main_layout.addWidget(wave_card, 1)

        # --- Pontos de corte (In / Out / Duração) ---
        cut_card = QFrame()
        cut_card.setObjectName("Card")
        cut_layout = QHBoxLayout(cut_card)
        cut_layout.setContentsMargins(14, 12, 14, 12)
        cut_layout.setSpacing(14)

        # Bloco Início
        in_box = QVBoxLayout()
        in_top = QHBoxLayout()
        lbl_in = QLabel("Início (IN)")
        lbl_in.setStyleSheet("color: #4ade80; font-weight: 600;")
        self.btn_mark_in = QPushButton("Marcar aqui (I)")
        self.btn_mark_in.clicked.connect(self._mark_in_at_playhead)
        in_top.addWidget(lbl_in)
        in_top.addStretch(1)
        in_top.addWidget(self.btn_mark_in)

        in_edit_row = QHBoxLayout()
        self.edit_start = QLineEdit("00:00.000")
        self.edit_start.editingFinished.connect(self._on_start_edited)
        self.btn_in_m1 = QPushButton("-1s")
        self.btn_in_m1.setObjectName("NudgeButton")
        self.btn_in_m1.clicked.connect(lambda: self._nudge_start(-1.0))
        self.btn_in_m01 = QPushButton("-0.1s")
        self.btn_in_m01.setObjectName("NudgeButton")
        self.btn_in_m01.clicked.connect(lambda: self._nudge_start(-0.1))
        self.btn_in_p01 = QPushButton("+0.1s")
        self.btn_in_p01.setObjectName("NudgeButton")
        self.btn_in_p01.clicked.connect(lambda: self._nudge_start(0.1))
        self.btn_in_p1 = QPushButton("+1s")
        self.btn_in_p1.setObjectName("NudgeButton")
        self.btn_in_p1.clicked.connect(lambda: self._nudge_start(1.0))

        in_edit_row.addWidget(self.edit_start, 1)
        in_edit_row.addWidget(self.btn_in_m1)
        in_edit_row.addWidget(self.btn_in_m01)
        in_edit_row.addWidget(self.btn_in_p01)
        in_edit_row.addWidget(self.btn_in_p1)
        in_box.addLayout(in_top)
        in_box.addLayout(in_edit_row)

        # Bloco Fim
        out_box = QVBoxLayout()
        out_top = QHBoxLayout()
        lbl_out = QLabel("Fim (OUT)")
        lbl_out.setStyleSheet("color: #fbbf24; font-weight: 600;")
        self.btn_mark_out = QPushButton("Marcar aqui (O)")
        self.btn_mark_out.clicked.connect(self._mark_out_at_playhead)
        out_top.addWidget(lbl_out)
        out_top.addStretch(1)
        out_top.addWidget(self.btn_mark_out)

        out_edit_row = QHBoxLayout()
        self.edit_end = QLineEdit("00:00.000")
        self.edit_end.editingFinished.connect(self._on_end_edited)
        self.btn_out_m1 = QPushButton("-1s")
        self.btn_out_m1.setObjectName("NudgeButton")
        self.btn_out_m1.clicked.connect(lambda: self._nudge_end(-1.0))
        self.btn_out_m01 = QPushButton("-0.1s")
        self.btn_out_m01.setObjectName("NudgeButton")
        self.btn_out_m01.clicked.connect(lambda: self._nudge_end(-0.1))
        self.btn_out_p01 = QPushButton("+0.1s")
        self.btn_out_p01.setObjectName("NudgeButton")
        self.btn_out_p01.clicked.connect(lambda: self._nudge_end(0.1))
        self.btn_out_p1 = QPushButton("+1s")
        self.btn_out_p1.setObjectName("NudgeButton")
        self.btn_out_p1.clicked.connect(lambda: self._nudge_end(1.0))

        out_edit_row.addWidget(self.edit_end, 1)
        out_edit_row.addWidget(self.btn_out_m1)
        out_edit_row.addWidget(self.btn_out_m01)
        out_edit_row.addWidget(self.btn_out_p01)
        out_edit_row.addWidget(self.btn_out_p1)
        out_box.addLayout(out_top)
        out_box.addLayout(out_edit_row)

        # Resumo do corte
        dur_box = QVBoxLayout()
        dur_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_dur_title = QLabel("Duração do Corte")
        lbl_dur_title.setObjectName("MetaLabel")
        lbl_dur_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cut_duration = QLabel("00:00.000")
        self.lbl_cut_duration.setStyleSheet(
            "font-family: Consolas; font-size: 17px; font-weight: 700; color: #38bdf8;"
        )
        self.lbl_cut_duration.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_reset_range = QPushButton("Selecionar Tudo")
        self.btn_reset_range.clicked.connect(self._reset_range)
        dur_box.addWidget(lbl_dur_title)
        dur_box.addWidget(self.lbl_cut_duration)
        dur_box.addWidget(self.btn_reset_range)

        cut_layout.addLayout(in_box, 2)
        cut_layout.addLayout(out_box, 2)
        cut_layout.addLayout(dur_box, 1)
        main_layout.addWidget(cut_card)

        # --- Exportação ---
        export_card = QFrame()
        export_card.setObjectName("Card")
        export_layout = QVBoxLayout(export_card)
        export_layout.setContentsMargins(14, 12, 14, 12)
        export_layout.setSpacing(8)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Salvar em:"))
        self.edit_output = QLineEdit()
        self.edit_output.setPlaceholderText("Escolha o arquivo de saída...")
        self.btn_browse_out = QPushButton("Alterar...")
        self.btn_browse_out.clicked.connect(self._on_browse_output)
        self.btn_export = QPushButton("Cortar e Salvar (Sem Perda)")
        self.btn_export.setObjectName("PrimaryButton")
        self.btn_export.clicked.connect(self._on_export_clicked)

        out_row.addWidget(self.edit_output, 1)
        out_row.addWidget(self.btn_browse_out)
        out_row.addWidget(self.btn_export)

        status_row = QHBoxLayout()
        self.lbl_status = QLabel("Pronto.")
        self.lbl_status.setObjectName("MetaLabel")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setFixedWidth(160)
        self.btn_open_folder = QPushButton("Abrir Pasta")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)

        status_row.addWidget(self.lbl_status, 1)
        status_row.addWidget(self.btn_open_folder)
        status_row.addWidget(self.progress)

        export_layout.addLayout(out_row)
        export_layout.addLayout(status_row)
        main_layout.addWidget(export_card)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self._toggle_play)
        QShortcut(QKeySequence("I"), self, activated=self._mark_in_at_playhead)
        QShortcut(QKeySequence("O"), self, activated=self._mark_out_at_playhead)
        QShortcut(QKeySequence("["), self, activated=lambda: self._seek_to(self._start_sec))
        QShortcut(QKeySequence("]"), self, activated=lambda: self._seek_to(self._end_sec))
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._on_open_clicked)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_export_clicked)

    def _update_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.btn_play,
            self.btn_play_sel,
            self.btn_stop,
            self.chk_loop,
            self.btn_zoom_in,
            self.btn_zoom_out,
            self.btn_zoom_reset,
            self.btn_mark_in,
            self.btn_mark_out,
            self.edit_start,
            self.edit_end,
            self.btn_in_m1,
            self.btn_in_m01,
            self.btn_in_p01,
            self.btn_in_p1,
            self.btn_out_m1,
            self.btn_out_m01,
            self.btn_out_p01,
            self.btn_out_p1,
            self.btn_reset_range,
            self.edit_output,
            self.btn_browse_out,
            self.btn_export,
        ):
            widget.setEnabled(enabled)

    # --- Drag & Drop ---
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile():
                path = Path(urls[0].toLocalFile())
                if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.load_file(Path(urls[0].toLocalFile()))

    # --- Abertura e carregamento ---
    def _on_open_clicked(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
        start_dir = str(self._audio_info.path.parent) if self._audio_info else str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo de áudio",
            start_dir,
            f"Arquivos de Áudio ({exts});;Todos os Arquivos (*.*)",
        )
        if file_path:
            self.load_file(Path(file_path))

    def load_file(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "Arquivo não encontrado", f"O arquivo não existe:\n{path}")
            return

        self._stop_playback()
        self._player.setSource(QUrl())
        self.waveform.clear_audio()
        self._update_controls_enabled(False)
        self.btn_open.setEnabled(False)
        self.btn_open_folder.setVisible(False)
        self.progress.setVisible(True)
        self.lbl_status.setText(f"Analisando '{path.name}'...")

        self._load_worker = LoadAudioWorker(path)
        self._load_worker.loaded.connect(self._on_audio_loaded)
        self._load_worker.failed.connect(self._on_audio_load_failed)
        self._load_worker.start()

    def _on_audio_loaded(self, info: AudioInfo, peaks) -> None:
        self._audio_info = info
        self._start_sec = 0.0
        self._end_sec = info.duration

        self.lbl_title.setText(info.display_title)
        self.lbl_meta.setText(f"{info.summary_text}  •  Duração: {format_time(info.duration)}")
        if info.codec_name.lower() == "flac" or info.path.suffix.lower() == ".flac":
            self.lbl_badge.setText("FLAC Lossless • Bit-Exact")
        else:
            self.lbl_badge.setText("Stream Copy • Sem Perda")

        self.waveform.set_audio(peaks, info.duration)
        self._sync_time_fields()

        suggested = info.path.with_name(f"{info.path.stem}_trim{info.path.suffix}")
        self.edit_output.setText(str(suggested))

        self._player.setSource(QUrl.fromLocalFile(str(info.path)))

        self.progress.setVisible(False)
        self.btn_open.setEnabled(True)
        self._update_controls_enabled(True)
        self.lbl_status.setText(
            "Dica: arraste as alças IN/OUT, use a roda do mouse para zoom e Espaço para tocar."
        )

    def _on_audio_load_failed(self, err: str) -> None:
        self.progress.setVisible(False)
        self.btn_open.setEnabled(True)
        self.lbl_status.setText("Erro ao carregar arquivo.")
        QMessageBox.critical(self, "Erro ao abrir áudio", err)

    # --- Sincronização de tempos ---
    def _sync_time_fields(self) -> None:
        self.edit_start.setText(format_time(self._start_sec))
        self.edit_end.setText(format_time(self._end_sec))
        self.lbl_cut_duration.setText(format_time(max(0.0, self._end_sec - self._start_sec)))

    def _on_waveform_range_changed(self, start_sec: float, end_sec: float) -> None:
        self._start_sec = start_sec
        self._end_sec = end_sec
        self._sync_time_fields()

    def _on_zoom_changed(self, zoom: float) -> None:
        self.lbl_zoom.setText(f"{zoom:.1f}x")

    def _on_start_edited(self) -> None:
        if not self._audio_info:
            return
        try:
            val = parse_time(self.edit_start.text())
        except ValueError:
            self._sync_time_fields()
            return
        val = max(0.0, min(val, self._end_sec - WaveformWidget.MIN_SELECTION_SEC))
        self._start_sec = val
        self.waveform.set_range(self._start_sec, self._end_sec)
        self._sync_time_fields()

    def _on_end_edited(self) -> None:
        if not self._audio_info:
            return
        try:
            val = parse_time(self.edit_end.text())
        except ValueError:
            self._sync_time_fields()
            return
        val = max(
            self._start_sec + WaveformWidget.MIN_SELECTION_SEC,
            min(val, self._audio_info.duration),
        )
        self._end_sec = val
        self.waveform.set_range(self._start_sec, self._end_sec)
        self._sync_time_fields()

    def _nudge_start(self, delta: float) -> None:
        if not self._audio_info:
            return
        self._start_sec = max(
            0.0,
            min(self._start_sec + delta, self._end_sec - WaveformWidget.MIN_SELECTION_SEC),
        )
        self.waveform.set_range(self._start_sec, self._end_sec)
        self._sync_time_fields()

    def _nudge_end(self, delta: float) -> None:
        if not self._audio_info:
            return
        self._end_sec = max(
            self._start_sec + WaveformWidget.MIN_SELECTION_SEC,
            min(self._end_sec + delta, self._audio_info.duration),
        )
        self.waveform.set_range(self._start_sec, self._end_sec)
        self._sync_time_fields()

    def _reset_range(self) -> None:
        if not self._audio_info:
            return
        self._start_sec = 0.0
        self._end_sec = self._audio_info.duration
        self.waveform.set_range(self._start_sec, self._end_sec)
        self._sync_time_fields()

    def _mark_in_at_playhead(self) -> None:
        if not self._audio_info:
            return
        pos = self._player.position() / 1000.0
        self._start_sec = max(
            0.0, min(pos, self._end_sec - WaveformWidget.MIN_SELECTION_SEC)
        )
        self.waveform.set_range(self._start_sec, self._end_sec)
        self._sync_time_fields()

    def _mark_out_at_playhead(self) -> None:
        if not self._audio_info:
            return
        pos = self._player.position() / 1000.0
        self._end_sec = max(
            self._start_sec + WaveformWidget.MIN_SELECTION_SEC,
            min(pos, self._audio_info.duration),
        )
        self.waveform.set_range(self._start_sec, self._end_sec)
        self._sync_time_fields()

    # --- Player ---
    def _toggle_play(self) -> None:
        if not self._audio_info:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._play_selection_only = False
            self._player.play()

    def _play_selection(self) -> None:
        if not self._audio_info:
            return
        self._play_selection_only = True
        self._player.setPosition(int(self._start_sec * 1000))
        self._player.play()

    def _stop_playback(self) -> None:
        self._play_selection_only = False
        self._player.stop()
        if self._audio_info:
            self.waveform.set_playhead(0.0)
            self.lbl_playhead.setText("00:00.000")

    def _seek_to(self, sec: float) -> None:
        if not self._audio_info:
            return
        sec = max(0.0, min(sec, self._audio_info.duration))
        self._player.setPosition(int(sec * 1000))
        self.waveform.set_playhead(sec)
        self.lbl_playhead.setText(format_time(sec))

    def _on_waveform_seek(self, sec: float) -> None:
        self._player.setPosition(int(sec * 1000))
        self.lbl_playhead.setText(format_time(sec))

    def _on_player_position_changed(self, pos_ms: int) -> None:
        sec = pos_ms / 1000.0
        self.waveform.set_playhead(sec)
        self.lbl_playhead.setText(format_time(sec))

        if self._play_selection_only and sec >= self._end_sec:
            if self.chk_loop.isChecked():
                self._player.setPosition(int(self._start_sec * 1000))
            else:
                self._player.pause()
                self._player.setPosition(int(self._start_sec * 1000))
                self._play_selection_only = False

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("Pausar (Espaço)")
        else:
            self.btn_play.setText("Tocar (Espaço)")

    # --- Exportação ---
    def _on_browse_output(self) -> None:
        if not self._audio_info:
            return
        ext = self._audio_info.path.suffix
        current_out = self.edit_output.text().strip() or str(
            self._audio_info.path.with_name(f"{self._audio_info.path.stem}_trim{ext}")
        )
        chosen, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar áudio cortado",
            current_out,
            f"Mesmo formato (*{ext});;Todos os Arquivos (*.*)",
        )
        if chosen:
            chosen_path = Path(chosen)
            if not chosen_path.suffix:
                chosen_path = chosen_path.with_suffix(ext)
            self.edit_output.setText(str(chosen_path))

    def _on_export_clicked(self) -> None:
        if not self._audio_info:
            return

        out_text = self.edit_output.text().strip()
        if not out_text:
            self._on_browse_output()
            out_text = self.edit_output.text().strip()
            if not out_text:
                return

        output_path = Path(out_text)
        if not output_path.suffix:
            output_path = output_path.with_suffix(self._audio_info.path.suffix)
            self.edit_output.setText(str(output_path))

        # Avisa se formato de saída for diferente do original (pois stream copy exige mesmo container/codec)
        if output_path.suffix.lower() != self._audio_info.path.suffix.lower():
            resp = QMessageBox.question(
                self,
                "Extensão diferente do original",
                f"Para cortar sem re-encodar (sem perda), recomenda-se manter a extensão original "
                f"({self._audio_info.path.suffix}).\n\n"
                f"Deseja alterar a saída para '{output_path.with_suffix(self._audio_info.path.suffix).name}'?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if resp == QMessageBox.StandardButton.Cancel:
                return
            if resp == QMessageBox.StandardButton.Yes:
                output_path = output_path.with_suffix(self._audio_info.path.suffix)
                self.edit_output.setText(str(output_path))

        overwriting_source = output_path.resolve() == self._audio_info.path.resolve()
        if output_path.exists():
            msg = (
                "Você escolheu sobrescrever o arquivo ORIGINAL. Essa ação não pode ser desfeita.\n\nContinuar?"
                if overwriting_source
                else f"O arquivo '{output_path.name}' já existe. Deseja substituí-lo?"
            )
            ans = QMessageBox.question(
                self,
                "Confirmar substituição",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        if overwriting_source:
            self._player.stop()
            self._player.setSource(QUrl())

        self._update_controls_enabled(False)
        self.btn_open.setEnabled(False)
        self.btn_open_folder.setVisible(False)
        self.progress.setVisible(True)
        self.lbl_status.setText("Cortando áudio sem re-encode...")

        self._trim_worker = TrimWorker(
            self._audio_info.path,
            output_path,
            self._start_sec,
            self._end_sec,
            self._audio_info,
        )
        self._trim_worker.finished_ok.connect(
            lambda res: self._on_trim_finished(res, reload_source=overwriting_source)
        )
        self._trim_worker.failed.connect(self._on_trim_failed)
        self._trim_worker.start()

    def _on_trim_finished(self, res: TrimResult, reload_source: bool) -> None:
        self.progress.setVisible(False)
        self.btn_open.setEnabled(True)
        self._update_controls_enabled(True)
        self._last_output_path = res.output_path
        self.btn_open_folder.setVisible(True)
        self.lbl_status.setText(
            f"Concluído ({res.mode_description}): '{res.output_path.name}' • {format_time(res.output_duration)}"
        )

        if reload_source:
            self.load_file(res.output_path)

    def _on_trim_failed(self, err: str) -> None:
        self.progress.setVisible(False)
        self.btn_open.setEnabled(True)
        self._update_controls_enabled(True)
        self.lbl_status.setText("Falha ao cortar o áudio.")
        if self._audio_info and self._player.source().isEmpty():
            self._player.setSource(QUrl.fromLocalFile(str(self._audio_info.path)))
        QMessageBox.critical(self, "Erro ao cortar", err)

    def _open_output_folder(self) -> None:
        if not self._last_output_path:
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(self._last_output_path)])
        else:
            os.startfile(str(self._last_output_path.parent))  # type: ignore[attr-defined]


def _resource_path(filename: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / filename


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)

    icon_path = _resource_path("app_icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    initial_file = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    win = AudioTrimmerWindow(initial_file=initial_file)
    if icon_path.exists():
        win.setWindowIcon(QIcon(str(icon_path)))
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
