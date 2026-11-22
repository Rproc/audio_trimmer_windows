from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SUPPORTED_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
    ".opus",
    ".wma",
    ".aiff",
    ".aif",
    ".mp4",
    ".webm",
    ".mka",
}


def _creation_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def ensure_ffmpeg_tools() -> tuple[str, str]:
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError(
            "FFmpeg e FFprobe não foram encontrados no PATH do sistema. "
            "Instale o FFmpeg para usar o corte sem perda de qualidade."
        )
    return ffmpeg_path, ffprobe_path


@dataclass
class AudioInfo:
    path: Path
    duration: float
    codec_name: str
    sample_rate: int
    channels: int
    bit_rate: int
    format_name: str
    has_cover_art: bool
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        artist = self.tags.get("artist") or self.tags.get("ARTIST") or ""
        title = self.tags.get("title") or self.tags.get("TITLE") or ""
        if artist and title:
            return f"{artist} — {title}"
        if title:
            return title
        return self.path.name

    @property
    def summary_text(self) -> str:
        codec = self.codec_name.upper() if self.codec_name else "?"
        sr = f"{self.sample_rate / 1000:.1f} kHz" if self.sample_rate else "? kHz"
        ch = (
            "Mono"
            if self.channels == 1
            else ("Estéreo" if self.channels == 2 else f"{self.channels} ch")
        )
        br = f"{self.bit_rate // 1000} kbps" if self.bit_rate > 0 else "Lossless / VBR"
        cover = "Com capa" if self.has_cover_art else "Sem capa"
        return f"{codec}  •  {br}  •  {sr}  •  {ch}  •  {cover}"


@dataclass
class TrimResult:
    output_path: Path
    mode_description: str
    output_duration: float


def format_time(seconds: float, include_ms: bool = True) -> str:
    seconds = max(0.0, float(seconds))
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_sec = total_ms // 1000
    hrs = total_sec // 3600
    mins = (total_sec % 3600) // 60
    secs = total_sec % 60
    if hrs > 0:
        base = f"{hrs:02d}:{mins:02d}:{secs:02d}"
    else:
        base = f"{mins:02d}:{secs:02d}"
    return f"{base}.{ms:03d}" if include_ms else base


def parse_time(text: str) -> float:
    """Converte strings como '01:23.450', '83.45', '1:02:03.5' para segundos."""
    cleaned = text.strip().replace(",", ".")
    if not cleaned:
        raise ValueError("Tempo vazio.")
    parts = cleaned.split(":")
    if len(parts) == 1:
        val = float(parts[0])
    elif len(parts) == 2:
        mins = int(parts[0])
        secs = float(parts[1])
        val = mins * 60 + secs
    elif len(parts) == 3:
        hrs = int(parts[0])
        mins = int(parts[1])
        secs = float(parts[2])
        val = hrs * 3600 + mins * 60 + secs
    else:
        raise ValueError(f"Formato de tempo inválido: {text}")
    if val < 0:
        raise ValueError("Tempo não pode ser negativo.")
    return val


def probe_audio(path: Path) -> AudioInfo:
    _, ffprobe_path = ensure_ffmpeg_tools()
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_creation_flags(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Falha ao ler arquivo com ffprobe:\n{proc.stderr.strip()}")

    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    fmt = data.get("format", {})

    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio_stream is None:
        raise RuntimeError("Nenhuma faixa de áudio encontrada neste arquivo.")

    has_cover_art = any(
        s.get("codec_type") == "video"
        and (
            s.get("disposition", {}).get("attached_pic") == 1
            or s.get("codec_name") in {"mjpeg", "png", "bmp", "webp"}
        )
        for s in streams
    )

    duration_raw = audio_stream.get("duration") or fmt.get("duration") or 0.0
    bit_rate_raw = audio_stream.get("bit_rate") or fmt.get("bit_rate") or 0

    tags: dict[str, str] = {}
    if isinstance(fmt.get("tags"), dict):
        tags.update({str(k): str(v) for k, v in fmt["tags"].items()})
    if isinstance(audio_stream.get("tags"), dict):
        for k, v in audio_stream["tags"].items():
            tags.setdefault(str(k), str(v))

    return AudioInfo(
        path=Path(path),
        duration=float(duration_raw),
        codec_name=str(audio_stream.get("codec_name") or ""),
        sample_rate=int(audio_stream.get("sample_rate") or 0),
        channels=int(audio_stream.get("channels") or 0),
        bit_rate=int(bit_rate_raw) if str(bit_rate_raw).isdigit() else 0,
        format_name=str(fmt.get("format_name") or ""),
        has_cover_art=has_cover_art,
        tags=tags,
    )


def extract_waveform_peaks(path: Path, num_bins: int = 2400) -> np.ndarray:
    """Extrai envelope (min, max) normalizado em [-1, 1] com shape (N, 2)."""
    ffmpeg_path, _ = ensure_ffmpeg_tools()
    cmd = [
        ffmpeg_path,
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "8000",
        "-f",
        "s16le",
        "-",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        creationflags=_creation_flags(),
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Falha ao decodificar forma de onda:\n{err}")

    raw = proc.stdout
    usable_len = len(raw) - (len(raw) % 2)
    if usable_len == 0:
        return np.zeros((1, 2), dtype=np.float32)

    samples = np.frombuffer(raw[:usable_len], dtype=np.int16).astype(np.float32) / 32768.0
    total = len(samples)
    bins = max(1, min(num_bins, total))

    edges = np.linspace(0, total, bins + 1, dtype=np.int64)
    peaks = np.empty((bins, 2), dtype=np.float32)
    for i in range(bins):
        seg = samples[edges[i] : edges[i + 1]]
        if seg.size == 0:
            peaks[i, 0] = 0.0
            peaks[i, 1] = 0.0
        else:
            peaks[i, 0] = float(seg.min())
            peaks[i, 1] = float(seg.max())

    max_abs = float(np.max(np.abs(peaks)))
    if max_abs > 1e-6:
        peaks = np.clip(peaks / max(max_abs, 0.25), -1.0, 1.0)
    return peaks


def trim_audio_lossless(
    input_path: Path,
    output_path: Path,
    start_sec: float,
    end_sec: float,
    audio_info: AudioInfo | None = None,
) -> TrimResult:
    """Corta o áudio sem perda de qualidade (stream copy ou FLAC bit-exact)."""
    ffmpeg_path, _ = ensure_ffmpeg_tools()
    input_path = Path(input_path)
    output_path = Path(output_path)

    if audio_info is None:
        audio_info = probe_audio(input_path)

    if start_sec < 0:
        start_sec = 0.0
    if end_sec <= start_sec:
        raise ValueError("O tempo final deve ser maior que o tempo inicial.")
    if audio_info.duration > 0 and end_sec > audio_info.duration + 0.05:
        end_sec = audio_info.duration

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ext = output_path.suffix or input_path.suffix
    temp_path = output_path.parent / f".trim_tmp_{uuid.uuid4().hex[:10]}{ext}"

    codec = audio_info.codec_name.lower()
    ext_lower = ext.lower()
    start_str = f"{start_sec:.6f}"
    end_str = f"{end_sec:.6f}"

    try:
        if codec == "flac" or ext_lower == ".flac":
            # FLAC raw stream-copy não atualiza o total_samples do cabeçalho STREAMINFO;
            # re-empacotar com -c:a flac é 100% lossless bit-a-bit e garante duração correta.
            cmd = [ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y"]
            cmd += ["-ss", start_str, "-to", end_str, "-i", str(input_path)]
            if audio_info.has_cover_art:
                cmd += [
                    "-i",
                    str(input_path),
                    "-map",
                    "0:a",
                    "-map",
                    "1:v",
                    "-c:a",
                    "flac",
                    "-c:v",
                    "copy",
                    "-map_metadata",
                    "1",
                    "-disposition:v",
                    "attached_pic",
                ]
            else:
                cmd += ["-map", "0:a", "-c:a", "flac", "-map_metadata", "0"]
            cmd.append(str(temp_path))
            mode_desc = "FLAC Lossless (bit-exact)"
        elif codec.startswith("pcm_") or ext_lower in {".wav", ".aiff", ".aif"}:
            cmd = [
                ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(input_path),
                "-ss",
                start_str,
                "-to",
                end_str,
                "-map",
                "0:a",
                "-c",
                "copy",
                "-map_metadata",
                "0",
                str(temp_path),
            ]
            mode_desc = "Stream Copy (PCM sem re-encode)"
        else:
            cmd = [ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y"]
            cmd += ["-ss", start_str, "-to", end_str, "-i", str(input_path)]
            if audio_info.has_cover_art:
                cmd += [
                    "-i",
                    str(input_path),
                    "-map",
                    "0:a",
                    "-map",
                    "1:v",
                    "-c",
                    "copy",
                    "-map_metadata",
                    "1",
                    "-disposition:v",
                    "attached_pic",
                ]
            else:
                cmd += ["-map", "0:a", "-c", "copy", "-map_metadata", "0"]
            cmd.append(str(temp_path))
            mode_desc = "Stream Copy (sem re-encode)"

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_creation_flags(),
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Erro no FFmpeg ao cortar o áudio:\n{proc.stderr.strip() or 'Código ' + str(proc.returncode)}"
            )

        out_info = probe_audio(temp_path)
        os.replace(temp_path, output_path)
        return TrimResult(
            output_path=output_path,
            mode_description=mode_desc,
            output_duration=out_info.duration,
        )
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
