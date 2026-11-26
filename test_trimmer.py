from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from audio_engine import (
    extract_waveform_peaks,
    format_time,
    parse_time,
    probe_audio,
    trim_audio_lossless,
)
from main import AudioTrimmerWindow
from themes import THEME_CLASSIC, THEME_MODERN


def _run_ffmpeg(*args: str) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg test setup failed: {proc.stderr}")


class TestAudioTrimmer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_time_formatting_and_parsing(self) -> None:
        self.assertEqual(format_time(0.0), "00:00.000")
        self.assertEqual(format_time(83.456), "01:23.456")
        self.assertEqual(format_time(3661.5), "01:01:01.500")
        self.assertAlmostEqual(parse_time("01:23.456"), 83.456, places=3)
        self.assertAlmostEqual(parse_time("83.45"), 83.45, places=3)
        self.assertAlmostEqual(parse_time("1:01:01.5"), 3661.5, places=3)
        with self.assertRaises(ValueError):
            parse_time("-2")

    def test_lossless_trim_mp3_with_cover_and_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / "song.mp3"
            out = tmp_dir / "song_trim.mp3"
            _run_ffmpeg(
                "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
                "-f", "lavfi", "-i", "color=c=red:s=64x64:d=1",
                "-map", "0:a", "-map", "1:v",
                "-c:a", "libmp3lame", "-b:a", "320k",
                "-c:v", "mjpeg", "-disposition:v", "attached_pic",
                "-id3v2_version", "3",
                "-metadata", "title=Faixa Teste",
                "-metadata", "artist=Banda X",
                str(src),
            )
            info = probe_audio(src)
            self.assertTrue(info.has_cover_art)
            self.assertEqual(info.codec_name, "mp3")
            self.assertEqual(info.tags.get("title"), "Faixa Teste")

            peaks = extract_waveform_peaks(src, num_bins=400)
            self.assertEqual(peaks.shape, (400, 2))

            res = trim_audio_lossless(src, out, 2.0, 5.5, info)
            self.assertTrue(out.exists())
            self.assertAlmostEqual(res.output_duration, 3.5, delta=0.15)
            out_info = probe_audio(out)
            self.assertTrue(out_info.has_cover_art)
            self.assertEqual(out_info.codec_name, "mp3")
            self.assertEqual(out_info.tags.get("title"), "Faixa Teste")
            self.assertEqual(out_info.tags.get("artist"), "Banda X")

    def test_lossless_trim_m4a_wav_flac_ogg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            cases = [
                ("in.m4a", ["-c:a", "aac", "-b:a", "192k"], "out.m4a"),
                ("in.wav", ["-c:a", "pcm_s16le"], "out.wav"),
                ("in.flac", ["-c:a", "flac"], "out.flac"),
                ("in.ogg", ["-c:a", "libvorbis", "-q:a", "5"], "out.ogg"),
            ]
            for in_name, enc_args, out_name in cases:
                src = tmp_dir / in_name
                out = tmp_dir / out_name
                _run_ffmpeg(
                    "-f", "lavfi", "-i", "sine=frequency=523.25:duration=6",
                    *enc_args, str(src)
                )
                info = probe_audio(src)
                res = trim_audio_lossless(src, out, 1.5, 4.5, info)
                self.assertTrue(out.exists(), msg=f"Missing output for {in_name}")
                self.assertAlmostEqual(res.output_duration, 3.0, delta=0.15, msg=in_name)

    def test_overwrite_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "inplace.mp3"
            _run_ffmpeg(
                "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                "-c:a", "libmp3lame", "-b:a", "192k", str(src),
            )
            res = trim_audio_lossless(src, src, 1.0, 3.5)
            self.assertAlmostEqual(res.output_duration, 2.5, delta=0.15)
            self.assertAlmostEqual(probe_audio(src).duration, 2.5, delta=0.15)

    def test_qt_window_load_and_nudge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "ui_test.mp3"
            _run_ffmpeg(
                "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
                "-c:a", "libmp3lame", "-b:a", "192k", str(src),
            )
            win = AudioTrimmerWindow()
            info = probe_audio(src)
            peaks = extract_waveform_peaks(src, num_bins=500)
            win._on_audio_loaded(info, peaks)

            self.assertTrue(win.btn_export.isEnabled())
            win._nudge_start(1.0)
            win._nudge_end(-1.0)
            self.assertAlmostEqual(win._start_sec, 1.0, places=3)
            self.assertAlmostEqual(win._end_sec, info.duration - 1.0, places=3)
            win.close()

    def test_theme_menu_switching_preserves_state(self) -> None:
        import numpy as np
        from PySide6.QtCore import QSettings
        from audio_engine import AudioInfo

        settings = QSettings(AudioTrimmerWindow.SETTINGS_ORG, AudioTrimmerWindow.SETTINGS_APP)
        prev_theme = settings.value(AudioTrimmerWindow.SETTINGS_THEME_KEY, None)

        win = AudioTrimmerWindow(initial_theme=THEME_MODERN)
        try:
            self.assertEqual(win.current_theme_id, THEME_MODERN)
            self.assertTrue(win._theme_actions[THEME_MODERN].isChecked())
            self.assertFalse(win._theme_actions[THEME_CLASSIC].isChecked())
            self.assertTrue(win.statusBar().isHidden())
            self.assertFalse(win.waveform._palette.classic_style)

            # Simula áudio carregado sem depender de ffmpeg
            fake_info = AudioInfo(
                path=Path("fake_song.mp3"),
                duration=12.0,
                codec_name="mp3",
                sample_rate=44100,
                channels=2,
                bit_rate=320000,
                format_name="mp3",
                has_cover_art=False,
                tags={"artist": "Artista", "title": "Música"},
            )
            fake_peaks = np.zeros((400, 2), dtype=np.float32)
            win._on_audio_loaded(fake_info, fake_peaks)
            win._nudge_start(2.0)
            win._nudge_end(-3.0)
            win.waveform.set_zoom(4.0)
            win.slider_vol.setValue(60)
            win.chk_loop.setChecked(True)
            win.edit_output.setText("custom_out.mp3")

            # Alterna para Clássico via ação do menu Tema
            win._theme_actions[THEME_CLASSIC].trigger()
            self.assertEqual(win.current_theme_id, THEME_CLASSIC)
            self.assertTrue(win._theme_actions[THEME_CLASSIC].isChecked())
            self.assertFalse(win.statusBar().isHidden())
            self.assertTrue(win.waveform._palette.classic_style)
            self.assertIsNotNone(win.btn_jump_in)
            self.assertIsNotNone(win.lbl_status_time)
            self.assertAlmostEqual(win._start_sec, 2.0, places=3)
            self.assertAlmostEqual(win._end_sec, 9.0, places=3)
            self.assertAlmostEqual(win.waveform.zoom_factor(), 4.0, places=2)
            self.assertEqual(win.slider_vol.value(), 60)
            self.assertTrue(win.chk_loop.isChecked())
            self.assertTrue(win.act_loop.isChecked())
            self.assertEqual(win.edit_output.text(), "custom_out.mp3")

            # Alterna de volta para Moderno via ação do menu Tema
            win._theme_actions[THEME_MODERN].trigger()
            self.assertEqual(win.current_theme_id, THEME_MODERN)
            self.assertTrue(win.statusBar().isHidden())
            self.assertFalse(win.waveform._palette.classic_style)
            self.assertIsNone(win.btn_jump_in)
            self.assertAlmostEqual(win._start_sec, 2.0, places=3)
            self.assertAlmostEqual(win._end_sec, 9.0, places=3)
            self.assertEqual(win.slider_vol.value(), 60)
            self.assertTrue(win.chk_loop.isChecked())
            self.assertEqual(win.edit_output.text(), "custom_out.mp3")
        finally:
            win.close()
            if prev_theme is None:
                settings.remove(AudioTrimmerWindow.SETTINGS_THEME_KEY)
            else:
                settings.setValue(AudioTrimmerWindow.SETTINGS_THEME_KEY, prev_theme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
