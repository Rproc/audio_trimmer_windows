from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
    QShortcut,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
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
from themes import (
    DARK_STYLESHEET,
    THEME_CLASSIC,
    THEME_MODERN,
    THEMES,
    build_qt_palette,
    get_theme,
    make_classic_icon,
)
from waveform_widget import WaveformWidget


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
    SETTINGS_ORG = "AudioTrimmer"
    SETTINGS_APP = "AudioTrimmer"
    SETTINGS_THEME_KEY = "ui/theme"

    def __init__(
        self,
        initial_file: Path | None = None,
        initial_theme: str | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Cortador de Áudio Sem Perda (Qt + FFmpeg)")
        self.resize(980, 640)
        self.setAcceptDrops(True)

        self._audio_info: AudioInfo | None = None
        self._peaks = None
        self._start_sec: float = 0.0
        self._end_sec: float = 0.0
        self._playhead_sec: float = 0.0
        self._play_selection_only: bool = False
        self._loop_enabled: bool = False
        self._volume_pct: int = 85
        self._output_text: str = ""
        self._status_text: str = "Pronto."
        self._is_busy: bool = False
        self._open_folder_visible: bool = False

        self._load_worker: LoadAudioWorker | None = None
        self._trim_worker: TrimWorker | None = None
        self._last_output_path: Path | None = None

        self._statusbar_widgets: list[QWidget] = []
        self._theme_actions: dict[str, QAction] = {}
        self.btn_jump_in: QPushButton | None = None
        self.btn_jump_out: QPushButton | None = None
        self.lbl_vol_pct: QLabel | None = None
        self.lbl_status_time: QLabel | None = None

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(self._volume_pct / 100.0)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_player_position_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)

        self._current_theme_id: str = self._resolve_initial_theme(initial_theme)

        self._build_menu_bar()
        self._setup_shortcuts()
        self.set_theme(self._current_theme_id, persist=False)

        if initial_file and initial_file.exists():
            self.load_file(initial_file)

    @property
    def current_theme_id(self) -> str:
        return self._current_theme_id

    def _resolve_initial_theme(self, initial_theme: str | None) -> str:
        if initial_theme in THEMES:
            return initial_theme
        settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
        saved = str(settings.value(self.SETTINGS_THEME_KEY, THEME_MODERN))
        return saved if saved in THEMES else THEME_MODERN

    # --- Menu Bar (inclui menu de Tema, sem switch) ---
    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        # Arquivo
        file_menu = menu_bar.addMenu("&Arquivo")
        self.act_open = QAction("Abrir Áudio...", self)
        self.act_open.setShortcut(QKeySequence("Ctrl+O"))
        self.act_open.triggered.connect(self._on_open_clicked)
        file_menu.addAction(self.act_open)

        self.act_export = QAction("Cortar e Salvar (Sem Perda)...", self)
        self.act_export.setShortcut(QKeySequence("Ctrl+S"))
        self.act_export.triggered.connect(self._on_export_clicked)
        file_menu.addAction(self.act_export)

        self.act_open_folder = QAction("Abrir Pasta de Saída", self)
        self.act_open_folder.triggered.connect(self._open_output_folder)
        file_menu.addAction(self.act_open_folder)

        file_menu.addSeparator()
        self.act_exit = QAction("Sair", self)
        self.act_exit.setShortcut(QKeySequence("Alt+F4"))
        self.act_exit.triggered.connect(self.close)
        file_menu.addAction(self.act_exit)

        # Reprodução
        play_menu = menu_bar.addMenu("&Reprodução")
        self.act_play = QAction("Tocar / Pausar\tEspaço", self)
        self.act_play.triggered.connect(self._toggle_play)
        play_menu.addAction(self.act_play)

        self.act_play_sel = QAction("Tocar Seleção", self)
        self.act_play_sel.triggered.connect(self._play_selection)
        play_menu.addAction(self.act_play_sel)

        self.act_stop = QAction("Parar", self)
        self.act_stop.triggered.connect(self._stop_playback)
        play_menu.addAction(self.act_stop)

        play_menu.addSeparator()
        self.act_loop = QAction("Repetir Seleção (Loop)", self)
        self.act_loop.setCheckable(True)
        self.act_loop.toggled.connect(self._set_loop_enabled)
        play_menu.addAction(self.act_loop)

        play_menu.addSeparator()
        self.act_jump_in = QAction("Ir para IN\t[", self)
        self.act_jump_in.triggered.connect(lambda: self._seek_to(self._start_sec))
        play_menu.addAction(self.act_jump_in)

        self.act_jump_out = QAction("Ir para OUT\t]", self)
        self.act_jump_out.triggered.connect(lambda: self._seek_to(self._end_sec))
        play_menu.addAction(self.act_jump_out)

        # Corte
        cut_menu = menu_bar.addMenu("&Corte")
        self.act_mark_in = QAction("Marcar IN no Cursor\tI", self)
        self.act_mark_in.triggered.connect(self._mark_in_at_playhead)
        cut_menu.addAction(self.act_mark_in)

        self.act_mark_out = QAction("Marcar OUT no Cursor\tO", self)
        self.act_mark_out.triggered.connect(self._mark_out_at_playhead)
        cut_menu.addAction(self.act_mark_out)

        self.act_reset_range = QAction("Selecionar Tudo", self)
        self.act_reset_range.triggered.connect(self._reset_range)
        cut_menu.addAction(self.act_reset_range)

        cut_menu.addSeparator()
        self.act_zoom_in = QAction("Aumentar Zoom (+)", self)
        self.act_zoom_in.triggered.connect(self._zoom_in)
        cut_menu.addAction(self.act_zoom_in)

        self.act_zoom_out = QAction("Diminuir Zoom (-)", self)
        self.act_zoom_out.triggered.connect(self._zoom_out)
        cut_menu.addAction(self.act_zoom_out)

        self.act_zoom_reset = QAction("Resetar Zoom (1.0x)", self)
        self.act_zoom_reset.triggered.connect(self._zoom_reset)
        cut_menu.addAction(self.act_zoom_reset)

        # Tema (menu exclusivo de seleção)
        theme_menu = menu_bar.addMenu("&Tema")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for theme_id, spec in THEMES.items():
            act = QAction(spec.name, self)
            act.setCheckable(True)
            act.setStatusTip(spec.description)
            act.setToolTip(spec.description)
            act.triggered.connect(lambda checked, tid=theme_id: checked and self.set_theme(tid))
            theme_group.addAction(act)
            theme_menu.addAction(act)
            self._theme_actions[theme_id] = act

    # --- Alternância de temas ---
    def set_theme(self, theme_id: str, persist: bool = True) -> None:
        spec = get_theme(theme_id)
        if self.centralWidget() is not None and spec.id == self._current_theme_id:
            return
        zoom = 1.0
        view_start = 0.0
        if hasattr(self, "waveform") and self.waveform is not None:
            zoom, view_start = self.waveform.view_state()
        if hasattr(self, "edit_output") and self.edit_output is not None:
            self._output_text = self.edit_output.text()

        self._current_theme_id = spec.id
        for tid, act in self._theme_actions.items():
            act.blockSignals(True)
            act.setChecked(tid == spec.id)
            act.blockSignals(False)

        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setPalette(build_qt_palette(spec.id))
            app.setStyleSheet(spec.stylesheet)
        else:
            self.setPalette(build_qt_palette(spec.id))
            self.setStyleSheet(spec.stylesheet)

        self._clear_status_bar()
        self.btn_jump_in = None
        self.btn_jump_out = None
        self.lbl_vol_pct = None
        self.lbl_status_time = None

        if spec.id == THEME_CLASSIC:
            self._build_classic_ui(spec.waveform_palette)
        else:
            self._build_modern_ui(spec.waveform_palette)

        self._restore_ui_state(zoom=zoom, view_start=view_start)

        if persist:
            settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)
            settings.setValue(self.SETTINGS_THEME_KEY, spec.id)

    def _clear_status_bar(self) -> None:
        sb = self.statusBar()
        for w in self._statusbar_widgets:
            sb.removeWidget(w)
            w.deleteLater()
        self._statusbar_widgets.clear()
        sb.clearMessage()

    # --- UI 1: Visual Atual (Moderno Escuro) ---
    def _build_modern_ui(self, wave_palette) -> None:
        self.statusBar().setVisible(False)

        root = QWidget(self)
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(16, 14, 16, 14)
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

        self.waveform = WaveformWidget(palette=wave_palette)
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
        self.chk_loop.toggled.connect(self._set_loop_enabled)

        self.lbl_playhead = QLabel("00:00.000")
        self.lbl_playhead.setObjectName("PlayheadLabel")

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
        self.btn_zoom_out.clicked.connect(self._zoom_out)

        self.lbl_zoom = QLabel("1.0x")
        self.lbl_zoom.setObjectName("ZoomLabel")
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setObjectName("NudgeButton")
        self.btn_zoom_in.clicked.connect(self._zoom_in)

        self.btn_zoom_reset = QPushButton("Reset Zoom")
        self.btn_zoom_reset.clicked.connect(self._zoom_reset)

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
        self.slider_vol.setValue(self._volume_pct)
        self.slider_vol.setFixedWidth(90)
        self.slider_vol.valueChanged.connect(self._on_volume_changed)
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
        lbl_in.setObjectName("InLabel")
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
        lbl_out.setObjectName("OutLabel")
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
        self.lbl_cut_duration.setObjectName("DurationLabel")
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
        self.edit_output.textChanged.connect(self._on_output_text_changed)
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

    # --- UI 2: Clássica (VLC / MPC) ---
    def _make_classic_divider(self) -> QFrame:
        div = QFrame()
        div.setObjectName("ClassicDivider")
        div.setFrameShape(QFrame.Shape.VLine)
        div.setFixedHeight(20)
        return div

    def _build_classic_ui(self, wave_palette) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(6, 6, 6, 4)
        main_layout.setSpacing(6)

        # --- Faixa superior compacta (estilo barra de mídia clássica) ---
        top_bar = QFrame()
        top_bar.setObjectName("ClassicHeaderBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(6, 4, 8, 4)
        top_layout.setSpacing(8)

        self.btn_open = QPushButton("Abrir...")
        self.btn_open.setIcon(make_classic_icon("open"))
        self.btn_open.setIconSize(QSize(14, 14))
        self.btn_open.setToolTip("Abrir arquivo de áudio (Ctrl+O)")
        self.btn_open.clicked.connect(self._on_open_clicked)

        self.lbl_title = QLabel("Nenhum arquivo carregado")
        self.lbl_title.setObjectName("TitleLabel")

        top_layout.addWidget(self.btn_open)
        top_layout.addWidget(self._make_classic_divider())
        top_layout.addWidget(self.lbl_title, 1)
        main_layout.addWidget(top_bar)

        # --- Viewport rebaixado (tela escura estilo MPC / VLC) ---
        viewport_frame = QFrame()
        viewport_frame.setObjectName("ClassicViewport")
        viewport_layout = QVBoxLayout(viewport_frame)
        viewport_layout.setContentsMargins(1, 1, 1, 1)
        viewport_layout.setSpacing(0)

        self.waveform = WaveformWidget(palette=wave_palette)
        self.waveform.rangeChanged.connect(self._on_waveform_range_changed)
        self.waveform.seekRequested.connect(self._on_waveform_seek)
        self.waveform.zoomChanged.connect(self._on_zoom_changed)
        viewport_layout.addWidget(self.waveform, 1)
        main_layout.addWidget(viewport_frame, 1)

        # --- Barra de transporte clássica (logo abaixo do viewport, estilo MPC/VLC) ---
        transport_bar = QFrame()
        transport_bar.setObjectName("ClassicTransportBar")
        transport = QHBoxLayout(transport_bar)
        transport.setContentsMargins(6, 4, 6, 4)
        transport.setSpacing(4)

        icon_sz = QSize(14, 14)

        self.btn_play = QPushButton()
        self.btn_play.setObjectName("ClassicToolButton")
        self.btn_play.setIcon(make_classic_icon("play"))
        self.btn_play.setIconSize(icon_sz)
        self.btn_play.setToolTip("Tocar / Pausar (Espaço)")
        self.btn_play.clicked.connect(self._toggle_play)

        self.btn_stop = QPushButton()
        self.btn_stop.setObjectName("ClassicToolButton")
        self.btn_stop.setIcon(make_classic_icon("stop"))
        self.btn_stop.setIconSize(icon_sz)
        self.btn_stop.setToolTip("Parar")
        self.btn_stop.clicked.connect(self._stop_playback)

        self.btn_play_sel = QPushButton()
        self.btn_play_sel.setObjectName("ClassicToolButton")
        self.btn_play_sel.setIcon(make_classic_icon("play_sel"))
        self.btn_play_sel.setIconSize(icon_sz)
        self.btn_play_sel.setToolTip("Tocar apenas a seleção (IN → OUT)")
        self.btn_play_sel.clicked.connect(self._play_selection)

        self.btn_jump_in = QPushButton()
        self.btn_jump_in.setObjectName("ClassicToolButton")
        self.btn_jump_in.setIcon(make_classic_icon("jump_in"))
        self.btn_jump_in.setIconSize(icon_sz)
        self.btn_jump_in.setToolTip("Ir para IN ([)")
        self.btn_jump_in.clicked.connect(lambda: self._seek_to(self._start_sec))

        self.btn_jump_out = QPushButton()
        self.btn_jump_out.setObjectName("ClassicToolButton")
        self.btn_jump_out.setIcon(make_classic_icon("jump_out"))
        self.btn_jump_out.setIconSize(icon_sz)
        self.btn_jump_out.setToolTip("Ir para OUT (])")
        self.btn_jump_out.clicked.connect(lambda: self._seek_to(self._end_sec))

        self.chk_loop = QCheckBox("Loop")
        self.chk_loop.setToolTip("Repetir trecho selecionado continuamente")
        self.chk_loop.toggled.connect(self._set_loop_enabled)

        self.lbl_playhead = QLabel("00:00.000")
        self.lbl_playhead.setObjectName("ClassicLcd")
        self.lbl_playhead.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_playhead.setMinimumWidth(84)

        transport.addWidget(self.btn_play)
        transport.addWidget(self.btn_stop)
        transport.addWidget(self.btn_play_sel)
        transport.addWidget(self.btn_jump_in)
        transport.addWidget(self.btn_jump_out)
        transport.addSpacing(4)
        transport.addWidget(self._make_classic_divider())
        transport.addSpacing(4)
        transport.addWidget(self.chk_loop)
        transport.addSpacing(4)
        transport.addWidget(self._make_classic_divider())
        transport.addSpacing(4)
        transport.addWidget(self.lbl_playhead)
        transport.addStretch(1)

        # Zoom clássico
        self.btn_zoom_out = QPushButton("-")
        self.btn_zoom_out.setObjectName("ClassicToolButton")
        self.btn_zoom_out.setToolTip("Diminuir zoom")
        self.btn_zoom_out.clicked.connect(self._zoom_out)

        self.lbl_zoom = QLabel("1.0x")
        self.lbl_zoom.setObjectName("ZoomLabel")
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setObjectName("ClassicToolButton")
        self.btn_zoom_in.setToolTip("Aumentar zoom")
        self.btn_zoom_in.clicked.connect(self._zoom_in)

        self.btn_zoom_reset = QPushButton("1:1")
        self.btn_zoom_reset.setObjectName("ClassicToolButton")
        self.btn_zoom_reset.setToolTip("Resetar zoom (1.0x)")
        self.btn_zoom_reset.clicked.connect(self._zoom_reset)

        lbl_zoom_title = QLabel("Zoom:")
        lbl_zoom_title.setStyleSheet("background: transparent;")
        transport.addWidget(lbl_zoom_title)
        transport.addWidget(self.btn_zoom_out)
        transport.addWidget(self.lbl_zoom)
        transport.addWidget(self.btn_zoom_in)
        transport.addWidget(self.btn_zoom_reset)
        transport.addSpacing(4)
        transport.addWidget(self._make_classic_divider())
        transport.addSpacing(4)

        # Volume clássico com ícone de alto-falante + percentual
        lbl_vol_icon = QLabel()
        lbl_vol_icon.setPixmap(make_classic_icon("volume").pixmap(15, 15))
        lbl_vol_icon.setStyleSheet("background: transparent;")
        lbl_vol_icon.setToolTip("Volume")

        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(self._volume_pct)
        self.slider_vol.setFixedWidth(92)
        self.slider_vol.valueChanged.connect(self._on_volume_changed)

        self.lbl_vol_pct = QLabel(f"{self._volume_pct}%")
        self.lbl_vol_pct.setStyleSheet(
            "background: transparent; font-family: Consolas; font-size: 11px; min-width: 32px;"
        )
        self.lbl_vol_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        transport.addWidget(lbl_vol_icon)
        transport.addWidget(self.slider_vol)
        transport.addWidget(self.lbl_vol_pct)
        main_layout.addWidget(transport_bar)

        # --- Grupo clássico: Pontos de Corte (IN / OUT) ---
        cut_group = QGroupBox("Pontos de Corte (IN / OUT)")
        cut_outer = QHBoxLayout(cut_group)
        cut_outer.setContentsMargins(8, 8, 8, 6)
        cut_outer.setSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(5)

        # Linha IN
        tag_in = QLabel("IN")
        tag_in.setObjectName("ClassicInTag")
        tag_in.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag_in.setFixedWidth(34)

        self.edit_start = QLineEdit("00:00.000")
        self.edit_start.setMinimumWidth(110)
        self.edit_start.editingFinished.connect(self._on_start_edited)

        self.btn_mark_in = QPushButton("Marcar (I)")
        self.btn_mark_in.clicked.connect(self._mark_in_at_playhead)

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

        grid.addWidget(tag_in, 0, 0)
        grid.addWidget(QLabel("Início:"), 0, 1)
        grid.addWidget(self.edit_start, 0, 2)
        grid.addWidget(self.btn_mark_in, 0, 3)
        grid.addWidget(self.btn_in_m1, 0, 4)
        grid.addWidget(self.btn_in_m01, 0, 5)
        grid.addWidget(self.btn_in_p01, 0, 6)
        grid.addWidget(self.btn_in_p1, 0, 7)

        # Linha OUT
        tag_out = QLabel("OUT")
        tag_out.setObjectName("ClassicOutTag")
        tag_out.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag_out.setFixedWidth(34)

        self.edit_end = QLineEdit("00:00.000")
        self.edit_end.setMinimumWidth(110)
        self.edit_end.editingFinished.connect(self._on_end_edited)

        self.btn_mark_out = QPushButton("Marcar (O)")
        self.btn_mark_out.clicked.connect(self._mark_out_at_playhead)

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

        grid.addWidget(tag_out, 1, 0)
        grid.addWidget(QLabel("Fim:"), 1, 1)
        grid.addWidget(self.edit_end, 1, 2)
        grid.addWidget(self.btn_mark_out, 1, 3)
        grid.addWidget(self.btn_out_m1, 1, 4)
        grid.addWidget(self.btn_out_m01, 1, 5)
        grid.addWidget(self.btn_out_p01, 1, 6)
        grid.addWidget(self.btn_out_p1, 1, 7)
        grid.setColumnStretch(2, 1)

        # Coluna direita: Duração + Selecionar Tudo
        cut_div = QFrame()
        cut_div.setObjectName("ClassicDivider")
        cut_div.setFrameShape(QFrame.Shape.VLine)

        dur_col = QVBoxLayout()
        dur_col.setSpacing(4)
        dur_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_dur_title = QLabel("Duração do corte")
        lbl_dur_title.setObjectName("MetaLabel")
        lbl_dur_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cut_duration = QLabel("00:00.000")
        self.lbl_cut_duration.setObjectName("ClassicDurationBox")
        self.lbl_cut_duration.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_reset_range = QPushButton("Selecionar Tudo")
        self.btn_reset_range.clicked.connect(self._reset_range)
        dur_col.addWidget(lbl_dur_title)
        dur_col.addWidget(self.lbl_cut_duration)
        dur_col.addWidget(self.btn_reset_range)

        cut_outer.addLayout(grid, 1)
        cut_outer.addWidget(cut_div)
        cut_outer.addLayout(dur_col)
        main_layout.addWidget(cut_group)

        # --- Grupo clássico: Exportação ---
        export_group = QGroupBox("Exportação (Sem Perda)")
        export_row = QHBoxLayout(export_group)
        export_row.setContentsMargins(8, 8, 8, 6)
        export_row.setSpacing(6)

        export_row.addWidget(QLabel("Salvar em:"))
        self.edit_output = QLineEdit()
        self.edit_output.setPlaceholderText("Escolha o arquivo de saída...")
        self.edit_output.textChanged.connect(self._on_output_text_changed)
        self.btn_browse_out = QPushButton("Procurar...")
        self.btn_browse_out.clicked.connect(self._on_browse_output)
        self.btn_export = QPushButton("Cortar e Salvar")
        self.btn_export.setObjectName("PrimaryButton")
        self.btn_export.setIcon(make_classic_icon("save"))
        self.btn_export.setIconSize(QSize(14, 14))
        self.btn_export.clicked.connect(self._on_export_clicked)

        export_row.addWidget(self.edit_output, 1)
        export_row.addWidget(self.btn_browse_out)
        export_row.addWidget(self.btn_export)
        main_layout.addWidget(export_group)

        # --- Barra de Status Clássica (estilo MPC-HC / VLC) ---
        sb = self.statusBar()
        sb.setVisible(True)
        sb.setSizeGripEnabled(True)

        self.lbl_status = QLabel("Pronto.")
        self.lbl_status.setObjectName("StatusCell")
        self.btn_open_folder = QPushButton("Abrir Pasta")
        self.btn_open_folder.setObjectName("NudgeButton")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setFixedWidth(130)

        self.lbl_meta = QLabel("Sem arquivo")
        self.lbl_meta.setObjectName("StatusCell")
        self.lbl_badge = QLabel("Stream Copy • Sem Perda")
        self.lbl_badge.setObjectName("BadgeLossless")
        self.lbl_status_time = QLabel("00:00.000 / 00:00.000")
        self.lbl_status_time.setObjectName("StatusTimeCell")

        sb.addWidget(self.lbl_status, 1)
        sb.addWidget(self.btn_open_folder)
        sb.addWidget(self.progress)
        sb.addPermanentWidget(self.lbl_meta)
        sb.addPermanentWidget(self.lbl_badge)
        sb.addPermanentWidget(self.lbl_status_time)

        self._statusbar_widgets = [
            self.lbl_status,
            self.btn_open_folder,
            self.progress,
            self.lbl_meta,
            self.lbl_badge,
            self.lbl_status_time,
        ]

    def _restore_ui_state(self, zoom: float = 1.0, view_start: float = 0.0) -> None:
        self.chk_loop.blockSignals(True)
        self.chk_loop.setChecked(self._loop_enabled)
        self.chk_loop.blockSignals(False)

        self.slider_vol.blockSignals(True)
        self.slider_vol.setValue(self._volume_pct)
        self.slider_vol.blockSignals(False)
        if self.lbl_vol_pct is not None:
            self.lbl_vol_pct.setText(f"{self._volume_pct}%")

        self.edit_output.blockSignals(True)
        self.edit_output.setText(self._output_text)
        self.edit_output.blockSignals(False)

        self.lbl_status.setText(self._status_text)
        self.progress.setVisible(self._is_busy)
        self.btn_open_folder.setVisible(self._open_folder_visible and not self._is_busy)

        if self._audio_info is not None:
            info = self._audio_info
            self.lbl_title.setText(info.display_title)
            if self._current_theme_id == THEME_CLASSIC:
                self.lbl_meta.setText(info.summary_text)
            else:
                self.lbl_meta.setText(
                    f"{info.summary_text}  •  Duração: {format_time(info.duration)}"
                )
            if info.codec_name.lower() == "flac" or info.path.suffix.lower() == ".flac":
                self.lbl_badge.setText("FLAC Lossless • Bit-Exact")
            else:
                self.lbl_badge.setText("Stream Copy • Sem Perda")

            if self._peaks is not None:
                self.waveform.set_audio(self._peaks, info.duration)
                self.waveform.set_range(self._start_sec, self._end_sec)
                self.waveform.set_playhead(self._playhead_sec)
                if zoom > 1.0 or view_start > 0.0:
                    self.waveform.restore_view_state(zoom, view_start)
            self._sync_time_fields()
        else:
            self.lbl_title.setText("Nenhum arquivo carregado")
            if self._current_theme_id == THEME_CLASSIC:
                self.lbl_meta.setText("Sem arquivo")
            else:
                self.lbl_meta.setText(
                    "Arraste MP3, M4A, WAV, FLAC, OGG, OPUS ou clique em Abrir Áudio"
                )
            self.lbl_badge.setText("Stream Copy • Sem Perda")
            self._sync_time_fields()

        self._update_playhead_labels(self._playhead_sec)
        self._update_play_button_visual(
            self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        self.btn_open.setEnabled(not self._is_busy)
        self.act_open.setEnabled(not self._is_busy)
        self._update_controls_enabled(self._audio_info is not None and not self._is_busy)

    # --- Atalhos ---
    def _shortcut_guard(self, callback) -> None:
        if isinstance(self.focusWidget(), QLineEdit):
            return
        callback()

    def _setup_shortcuts(self) -> None:
        QShortcut(
            QKeySequence(Qt.Key.Key_Space),
            self,
            activated=lambda: self._shortcut_guard(self._toggle_play),
        )
        QShortcut(
            QKeySequence("I"),
            self,
            activated=lambda: self._shortcut_guard(self._mark_in_at_playhead),
        )
        QShortcut(
            QKeySequence("O"),
            self,
            activated=lambda: self._shortcut_guard(self._mark_out_at_playhead),
        )
        QShortcut(
            QKeySequence("["),
            self,
            activated=lambda: self._shortcut_guard(lambda: self._seek_to(self._start_sec)),
        )
        QShortcut(
            QKeySequence("]"),
            self,
            activated=lambda: self._shortcut_guard(lambda: self._seek_to(self._end_sec)),
        )

    def _update_controls_enabled(self, enabled: bool) -> None:
        widgets = [
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
        ]
        if self.btn_jump_in is not None:
            widgets.append(self.btn_jump_in)
        if self.btn_jump_out is not None:
            widgets.append(self.btn_jump_out)
        for widget in widgets:
            widget.setEnabled(enabled)

        for act in (
            self.act_export,
            self.act_play,
            self.act_play_sel,
            self.act_stop,
            self.act_loop,
            self.act_jump_in,
            self.act_jump_out,
            self.act_mark_in,
            self.act_mark_out,
            self.act_reset_range,
            self.act_zoom_in,
            self.act_zoom_out,
            self.act_zoom_reset,
        ):
            act.setEnabled(enabled)

        self.act_open_folder.setEnabled(bool(self._last_output_path) and not self._is_busy)

    # --- Helpers de estado sincronizado ---
    def _set_status(self, text: str) -> None:
        self._status_text = text
        self.lbl_status.setText(text)

    def _set_loop_enabled(self, checked: bool) -> None:
        self._loop_enabled = bool(checked)
        if hasattr(self, "chk_loop") and self.chk_loop.isChecked() != self._loop_enabled:
            self.chk_loop.blockSignals(True)
            self.chk_loop.setChecked(self._loop_enabled)
            self.chk_loop.blockSignals(False)
        if self.act_loop.isChecked() != self._loop_enabled:
            self.act_loop.blockSignals(True)
            self.act_loop.setChecked(self._loop_enabled)
            self.act_loop.blockSignals(False)

    def _on_volume_changed(self, value: int) -> None:
        self._volume_pct = int(value)
        self._audio_output.setVolume(self._volume_pct / 100.0)
        if self.lbl_vol_pct is not None:
            self.lbl_vol_pct.setText(f"{self._volume_pct}%")

    def _on_output_text_changed(self, text: str) -> None:
        self._output_text = text

    def _zoom_in(self) -> None:
        self.waveform.set_zoom(self.waveform.zoom_factor() * 1.4)

    def _zoom_out(self) -> None:
        self.waveform.set_zoom(self.waveform.zoom_factor() * 0.7)

    def _zoom_reset(self) -> None:
        self.waveform.reset_zoom()

    def _update_playhead_labels(self, sec: float) -> None:
        self._playhead_sec = max(0.0, float(sec))
        cur_str = format_time(self._playhead_sec)
        self.lbl_playhead.setText(cur_str)
        if self.lbl_status_time is not None:
            total = self._audio_info.duration if self._audio_info else 0.0
            self.lbl_status_time.setText(f"{cur_str} / {format_time(total)}")

    def _update_play_button_visual(self, playing: bool) -> None:
        if self._current_theme_id == THEME_CLASSIC:
            self.btn_play.setText("")
            self.btn_play.setIcon(make_classic_icon("pause" if playing else "play"))
            self.btn_play.setToolTip("Pausar (Espaço)" if playing else "Tocar (Espaço)")
        else:
            self.btn_play.setIcon(QIcon())
            self.btn_play.setText("Pausar (Espaço)" if playing else "Tocar (Espaço)")

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
        self._peaks = None
        self.waveform.clear_audio()
        self._is_busy = True
        self._open_folder_visible = False
        self._update_controls_enabled(False)
        self.btn_open.setEnabled(False)
        self.act_open.setEnabled(False)
        self.btn_open_folder.setVisible(False)
        self.progress.setVisible(True)
        self._set_status(f"Analisando '{path.name}'...")

        self._load_worker = LoadAudioWorker(path)
        self._load_worker.loaded.connect(self._on_audio_loaded)
        self._load_worker.failed.connect(self._on_audio_load_failed)
        self._load_worker.start()

    def _on_audio_loaded(self, info: AudioInfo, peaks) -> None:
        self._audio_info = info
        self._peaks = peaks
        self._start_sec = 0.0
        self._end_sec = info.duration
        self._playhead_sec = 0.0
        self._is_busy = False

        self.lbl_title.setText(info.display_title)
        if self._current_theme_id == THEME_CLASSIC:
            self.lbl_meta.setText(info.summary_text)
        else:
            self.lbl_meta.setText(f"{info.summary_text}  •  Duração: {format_time(info.duration)}")

        if info.codec_name.lower() == "flac" or info.path.suffix.lower() == ".flac":
            self.lbl_badge.setText("FLAC Lossless • Bit-Exact")
        else:
            self.lbl_badge.setText("Stream Copy • Sem Perda")

        self.waveform.set_audio(peaks, info.duration)
        self._sync_time_fields()
        self._update_playhead_labels(0.0)

        suggested = info.path.with_name(f"{info.path.stem}_trim{info.path.suffix}")
        self._output_text = str(suggested)
        self.edit_output.setText(self._output_text)

        self._player.setSource(QUrl.fromLocalFile(str(info.path)))

        self.progress.setVisible(False)
        self.btn_open.setEnabled(True)
        self.act_open.setEnabled(True)
        self._update_controls_enabled(True)
        self._set_status(
            "Dica: arraste as alças IN/OUT, use a roda do mouse para zoom e Espaço para tocar."
        )

    def _on_audio_load_failed(self, err: str) -> None:
        self._is_busy = False
        self.progress.setVisible(False)
        self.btn_open.setEnabled(True)
        self.act_open.setEnabled(True)
        self._update_controls_enabled(self._audio_info is not None)
        self._set_status("Erro ao carregar arquivo.")
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
            self._update_playhead_labels(0.0)

    def _seek_to(self, sec: float) -> None:
        if not self._audio_info:
            return
        sec = max(0.0, min(sec, self._audio_info.duration))
        self._player.setPosition(int(sec * 1000))
        self.waveform.set_playhead(sec)
        self._update_playhead_labels(sec)

    def _on_waveform_seek(self, sec: float) -> None:
        self._player.setPosition(int(sec * 1000))
        self._update_playhead_labels(sec)

    def _on_player_position_changed(self, pos_ms: int) -> None:
        sec = pos_ms / 1000.0
        self.waveform.set_playhead(sec)
        self._update_playhead_labels(sec)

        if self._play_selection_only and sec >= self._end_sec:
            if self._loop_enabled:
                self._player.setPosition(int(self._start_sec * 1000))
            else:
                self._player.pause()
                self._player.setPosition(int(self._start_sec * 1000))
                self._play_selection_only = False

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self._update_play_button_visual(state == QMediaPlayer.PlaybackState.PlayingState)

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
            self._output_text = str(chosen_path)
            self.edit_output.setText(self._output_text)

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
            self._output_text = str(output_path)
            self.edit_output.setText(self._output_text)

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
                self._output_text = str(output_path)
                self.edit_output.setText(self._output_text)

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

        self._is_busy = True
        self._open_folder_visible = False
        self._update_controls_enabled(False)
        self.btn_open.setEnabled(False)
        self.act_open.setEnabled(False)
        self.btn_open_folder.setVisible(False)
        self.progress.setVisible(True)
        self._set_status("Cortando áudio sem re-encode...")

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
        self._is_busy = False
        self.progress.setVisible(False)
        self.btn_open.setEnabled(True)
        self.act_open.setEnabled(True)
        self._last_output_path = res.output_path
        self._open_folder_visible = True
        self._update_controls_enabled(True)
        self.btn_open_folder.setVisible(True)
        self._set_status(
            f"Concluído ({res.mode_description}): '{res.output_path.name}' • {format_time(res.output_duration)}"
        )

        if reload_source:
            self.load_file(res.output_path)

    def _on_trim_failed(self, err: str) -> None:
        self._is_busy = False
        self.progress.setVisible(False)
        self.btn_open.setEnabled(True)
        self.act_open.setEnabled(True)
        self._update_controls_enabled(True)
        self._set_status("Falha ao cortar o áudio.")
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
