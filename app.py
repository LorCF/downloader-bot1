"""
Universal Media Downloader & Studio
Apple macOS / iOS Premium Design System
CustomTkinter, yt-dlp ve FFmpeg teknolojileri ile geliştirilmiştir.
"""

import os
import sys
import re
import shutil
import threading
import time
import subprocess
import urllib.request
from io import BytesIO
from typing import Optional, Dict, Any, Callable, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk
import yt_dlp

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


class TimeParser:
    """Zaman dönüştürme ve biçimlendirme yardımcı sınıfı."""

    @staticmethod
    def parse_time(time_str: str) -> Optional[float]:
        if not time_str or not time_str.strip():
            return None
        time_str = time_str.strip()
        parts = time_str.split(':')
        try:
            if len(parts) == 1:
                val = float(parts[0])
                if val < 0:
                    raise ValueError("Zaman değeri negatif olamaz.")
                return val
            elif len(parts) == 2:
                mins = float(parts[0])
                secs = float(parts[1])
                if mins < 0 or secs < 0:
                    raise ValueError("Zaman değerleri negatif olamaz.")
                return mins * 60 + secs
            elif len(parts) == 3:
                hrs = float(parts[0])
                mins = float(parts[1])
                secs = float(parts[2])
                if hrs < 0 or mins < 0 or secs < 0:
                    raise ValueError("Zaman değerleri negatif olamaz.")
                return hrs * 3600 + mins * 60 + secs
            else:
                raise ValueError("Geçersiz zaman biçimi.")
        except ValueError as e:
            raise ValueError(f"Geçersiz zaman: '{time_str}'. Örnekler: 00:01:20, 01:20 veya 80") from e

    @staticmethod
    def format_duration(seconds: Optional[float], force_hours: bool = True) -> str:
        if seconds is None or seconds < 0:
            return "00:00:00" if force_hours else "--:--"
        total_secs = int(round(seconds))
        hours, remainder = divmod(total_secs, 3600)
        minutes, secs = divmod(remainder, 60)
        if force_hours or hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def format_bytes(bytes_count: Optional[float]) -> str:
        if not bytes_count or bytes_count <= 0:
            return "0 MB"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.1f} PB"

    @staticmethod
    def format_speed(speed_bytes_per_sec: Optional[float]) -> str:
        if not speed_bytes_per_sec or speed_bytes_per_sec <= 0:
            return "0 KB/s"
        if speed_bytes_per_sec < 1024 * 1024:
            return f"{speed_bytes_per_sec / 1024:.1f} KB/s"
        return f"{speed_bytes_per_sec / (1024 * 1024):.2f} MB/s"


class FFmpegHelper:
    """FFmpeg yürütülebilir dosyasını tespit eden ve doğrulayan yardımcı sınıf."""

    _cached_path: Optional[str] = None

    @classmethod
    def get_ffmpeg_path(cls) -> Optional[str]:
        if cls._cached_path and os.path.exists(cls._cached_path):
            return cls._cached_path

        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            cls._cached_path = system_ffmpeg
            return system_ffmpeg

        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_candidates = [
            os.path.join(base_dir, "ffmpeg.exe"),
            os.path.join(base_dir, "bin", "ffmpeg.exe"),
            os.path.join(base_dir, "ffmpeg", "bin", "ffmpeg.exe")
        ]
        for candidate in local_candidates:
            if os.path.exists(candidate):
                cls._cached_path = candidate
                return candidate

        if imageio_ffmpeg is not None:
            try:
                exe = imageio_ffmpeg.get_ffmpeg_exe()
                if exe and os.path.exists(exe):
                    cls._cached_path = exe
                    return exe
            except Exception:
                pass

        return None


class YtDlpCustomLogger:
    """yt-dlp log mesajlarını yakalayan özel logger sınıfı."""

    def __init__(self, log_callback: Optional[Callable[[str], None]] = None):
        self.log_callback = log_callback

    def debug(self, msg: str):
        if self.log_callback and not msg.startswith("[debug]"):
            self.log_callback(f"[Bilgi] {msg}")

    def info(self, msg: str):
        if self.log_callback:
            self.log_callback(f"[Bilgi] {msg}")

    def warning(self, msg: str):
        if self.log_callback:
            self.log_callback(f"[Uyarı] {msg}")

    def error(self, msg: str):
        if self.log_callback:
            self.log_callback(f"[Hata] {msg}")


class AppleButton(ctk.CTkButton):
    """
    Apple macOS tarzı animasyonlu, orantılı ve yuvarlatılmış buton (Pill Button).
    Gereksiz boydan boya uzamaz, zarif boyutlara ve canlı hover efektlerine sahiptir.
    """

    def __init__(self, master, **kwargs):
        if "corner_radius" not in kwargs:
            kwargs["corner_radius"] = 8
        if "font" not in kwargs:
            kwargs["font"] = ctk.CTkFont(family="SF Pro Text", size=12, weight="bold")
        if "height" not in kwargs:
            kwargs["height"] = 32
        super().__init__(master, **kwargs)
        self.configure(cursor="hand2")


class CTkRangeSlider(ctk.CTkFrame):
    """
    Apple Final Cut / QuickTime tarzı çift tutamaçlı görsel zaman kaydırıcı.
    """

    def __init__(
        self,
        master,
        from_: float = 0.0,
        to: float = 100.0,
        start_val: float = 0.0,
        end_val: float = 100.0,
        command: Optional[Callable[[float, float], None]] = None,
        height: int = 36,
        **kwargs
    ):
        super().__init__(master, height=height, fg_color="transparent", **kwargs)
        self.from_ = float(from_)
        self.to = max(float(to), self.from_ + 0.1)
        self.start_val = max(self.from_, min(float(start_val), self.to))
        self.end_val = max(self.start_val, min(float(end_val), self.to))
        self.command = command
        self.is_enabled = True

        self.handle_width = 16
        self.handle_height = 24
        self.track_height = 14
        self.padding_x = 12
        self.active_handle: Optional[str] = None

        self.canvas = ctk.CTkCanvas(
            self,
            height=height,
            highlightthickness=0,
            borderwidth=0
        )
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)

        self._draw_slider()

    def _draw(self, *args, **kwargs):
        super()._draw(*args, **kwargs)
        if hasattr(self, 'canvas'):
            self._draw_slider()

    def _get_canvas_bg(self) -> str:
        mode = ctk.get_appearance_mode().lower()
        if mode == "light":
            return "#ffffff"
        return "#242426"

    def _draw_rounded_rect(self, x1: float, y1: float, x2: float, y2: float, r: float, **kwargs):
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        r = min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0)
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def _draw_slider(self):
        if not hasattr(self, 'canvas'):
            return
        self.canvas.delete("all")
        w = max(self.canvas.winfo_width(), 100)
        h = max(self.canvas.winfo_height(), 36)

        bg_color = self._get_canvas_bg()
        self.canvas.configure(bg=bg_color)

        mode = ctk.get_appearance_mode().lower()
        track_bg = "#38383c" if mode == "dark" else "#e5e5ea"
        highlight_color = "#0071e3" if mode == "dark" else "#0071e3"
        handle_fill = "#ffffff"
        handle_border = "#8e8e93" if mode == "dark" else "#aeaeb2"

        usable_w = max(w - (2 * self.padding_x), 10)
        range_span = max(self.to - self.from_, 0.001)

        x_start = self.padding_x + ((self.start_val - self.from_) / range_span) * usable_w
        x_end = self.padding_x + ((self.end_val - self.from_) / range_span) * usable_w

        track_top = (h - self.track_height) / 2.0
        track_bot = track_top + self.track_height

        self._draw_rounded_rect(
            self.padding_x,
            track_top,
            w - self.padding_x,
            track_bot,
            r=self.track_height / 2.0,
            fill=track_bg,
            outline=""
        )

        if x_end > x_start:
            self._draw_rounded_rect(
                x_start,
                track_top,
                x_end,
                track_bot,
                r=self.track_height / 2.0,
                fill=highlight_color,
                outline=""
            )

        h_top = (h - self.handle_height) / 2.0
        h_bot = h_top + self.handle_height
        hw = self.handle_width / 2.0

        self._draw_rounded_rect(
            x_start - hw,
            h_top,
            x_start + hw,
            h_bot,
            r=4,
            fill=handle_fill,
            outline=handle_border,
            width=1.5
        )

        self._draw_rounded_rect(
            x_end - hw,
            h_top,
            x_end + hw,
            h_bot,
            r=4,
            fill=handle_fill,
            outline=handle_border,
            width=1.5
        )

    def _val_from_x(self, x: float) -> float:
        w = max(self.canvas.winfo_width(), 100)
        usable_w = max(w - (2 * self.padding_x), 10)
        fraction = (x - self.padding_x) / usable_w
        fraction = max(0.0, min(1.0, fraction))
        val = self.from_ + fraction * (self.to - self.from_)
        return val

    def _get_handle_positions(self) -> Tuple[float, float]:
        w = max(self.canvas.winfo_width(), 100)
        usable_w = max(w - (2 * self.padding_x), 10)
        range_span = max(self.to - self.from_, 0.001)
        x_start = self.padding_x + ((self.start_val - self.from_) / range_span) * usable_w
        x_end = self.padding_x + ((self.end_val - self.from_) / range_span) * usable_w
        return x_start, x_end

    def _on_press(self, event):
        x_start, x_end = self._get_handle_positions()
        dist_start = abs(event.x - x_start)
        dist_end = abs(event.x - x_end)
        tolerance = 16

        if dist_start <= tolerance and dist_start <= dist_end:
            self.active_handle = 'start'
        elif dist_end <= tolerance:
            self.active_handle = 'end'
        else:
            if dist_start < dist_end:
                self.active_handle = 'start'
                self.start_val = min(self._val_from_x(event.x), self.end_val)
            else:
                self.active_handle = 'end'
                self.end_val = max(self._val_from_x(event.x), self.start_val)
            self._draw_slider()
            if self.command:
                self.command(self.start_val, self.end_val)

    def _on_drag(self, event):
        if not self.active_handle:
            return

        new_val = self._val_from_x(event.x)
        if self.active_handle == 'start':
            self.start_val = max(self.from_, min(new_val, self.end_val))
        elif self.active_handle == 'end':
            self.end_val = max(self.start_val, min(new_val, self.to))

        self._draw_slider()
        if self.command:
            self.command(self.start_val, self.end_val)

    def _on_release(self, event):
        self.active_handle = None

    def _on_hover(self, event):
        x_start, x_end = self._get_handle_positions()
        dist_start = abs(event.x - x_start)
        dist_end = abs(event.x - x_end)
        if dist_start <= 14 or dist_end <= 14:
            self.canvas.configure(cursor="sb_h_double_arrow")
        else:
            self.canvas.configure(cursor="hand2")

    def _on_resize(self, event):
        self._draw_slider()

    def set_range(self, from_: float, to: float, reset_values: bool = False):
        self.from_ = float(from_)
        self.to = max(float(to), self.from_ + 0.1)
        if reset_values:
            self.start_val = self.from_
            self.end_val = self.to
        else:
            self.start_val = max(self.from_, min(self.start_val, self.to))
            self.end_val = max(self.start_val, min(self.end_val, self.to))
        self._draw_slider()

    def set_values(self, start_val: float, end_val: float, trigger_callback: bool = True):
        self.start_val = max(self.from_, min(float(start_val), self.to))
        self.end_val = max(self.start_val, min(float(end_val), self.to))
        self._draw_slider()
        if trigger_callback and self.command:
            self.command(self.start_val, self.end_val)

    def get_values(self) -> Tuple[float, float]:
        return self.start_val, self.end_val


class DownloaderEngine:
    """yt-dlp ve FFmpeg işlemlerini yöneten çekirdek indirme motoru."""

    QUALITY_FORMAT_MAP = {
        "En Yüksek (Best)": "bestvideo+bestaudio/best",
        "4K (2160p)": "bestvideo[height<=2160]+bestaudio/best[height<=2160]/best",
        "2K (1440p)": "bestvideo[height<=1440]+bestaudio/best[height<=1440]/best",
        "1080p (Full HD)": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "720p (HD)": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "480p (SD)": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
        "360p (Düşük)": "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
    }

    AUDIO_BITRATE_MAP = {
        "320 kbps (En Yüksek)": "320",
        "256 kbps (Yüksek)": "256",
        "192 kbps (Standart)": "192",
        "128 kbps (Düşük)": "128",
        "64 kbps (Minimum)": "64",
    }

    def __init__(self):
        self.is_cancelled = False
        self.last_downloaded_file: Optional[str] = None

    def cancel(self):
        self.is_cancelled = True

    def fetch_info(self, url: str) -> Dict[str, Any]:
        """Video veya ses linkinden önizleme bilgilerini çeker."""
        ffmpeg_exe = FFmpegHelper.get_ffmpeg_path()
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
        }
        if ffmpeg_exe:
            ydl_opts['ffmpeg_location'] = ffmpeg_exe

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info

    def download(
        self,
        url: str,
        output_dir: str,
        format_type: str,
        quality: str,
        custom_title: Optional[str],
        trim_enabled: bool,
        start_time_sec: Optional[float],
        end_time_sec: Optional[float],
        progress_callback: Callable[[Dict[str, Any]], None],
        status_callback: Callable[[str, str], None],
        log_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """İndirme, dönüştürme ve kırpma işlemini gerçekleştirir."""
        self.is_cancelled = False
        self.last_downloaded_file = None

        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        ffmpeg_exe = FFmpegHelper.get_ffmpeg_path()

        if custom_title and custom_title.strip():
            clean_name = re.sub(r'[\\/*?:"<>|]', "", custom_title).strip()
            if not clean_name:
                clean_name = "Video"
            outtmpl = os.path.join(output_dir, f"{clean_name}.%(ext)s")
        else:
            outtmpl = os.path.join(output_dir, "%(title).120B [%(id)s].%(ext)s")

        if trim_enabled and start_time_sec is not None and end_time_sec is not None:
            if end_time_sec <= start_time_sec:
                raise ValueError("Bitiş zamanı başlangıç zamanından büyük olmalıdır.")

        def ydl_progress_hook(d: Dict[str, Any]):
            if self.is_cancelled:
                raise yt_dlp.utils.DownloadCancelled("Kullanıcı indirmeyi iptal etti.")

            status = d.get('status')
            if status == 'downloading':
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                speed = d.get('speed') or 0
                eta = d.get('eta')
                
                percent = 0.0
                if total_bytes > 0:
                    percent = (downloaded / total_bytes) * 100.0
                elif '_percent_str' in d:
                    clean_pct = re.sub(r'[^\d.]', '', d['_percent_str'])
                    try:
                        percent = float(clean_pct)
                    except ValueError:
                        percent = 0.0

                progress_data = {
                    'percent': percent,
                    'downloaded_bytes': downloaded,
                    'total_bytes': total_bytes,
                    'speed': speed,
                    'eta': eta,
                    'filename': d.get('filename', '')
                }
                progress_callback(progress_data)

            elif status == 'finished':
                downloaded_file = d.get('filename')
                if downloaded_file:
                    self.last_downloaded_file = downloaded_file
                status_callback("İndirme tamamlandı, işleniyor...", "processing")

        def ydl_postprocessor_hook(d: Dict[str, Any]):
            if self.is_cancelled:
                raise yt_dlp.utils.DownloadCancelled("Kullanıcı işlemi iptal etti.")
            
            status = d.get('status')
            postprocessor = d.get('postprocessor', '')
            if status == 'started':
                status_callback(f"İşleniyor: {postprocessor}...", "processing")
            elif status == 'finished':
                if 'filepath' in d:
                    self.last_downloaded_file = d['filepath']

        ydl_opts: Dict[str, Any] = {
            'outtmpl': outtmpl,
            'progress_hooks': [ydl_progress_hook],
            'postprocessor_hooks': [ydl_postprocessor_hook],
            'logger': YtDlpCustomLogger(log_callback),
            'windowsfilenames': True,
            'overwrites': True,
            'no_color': True,
        }

        if ffmpeg_exe:
            ydl_opts['ffmpeg_location'] = ffmpeg_exe

        if trim_enabled and (start_time_sec is not None or end_time_sec is not None):
            ranges = [(start_time_sec or 0.0, end_time_sec or float('inf'))]
            ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, ranges)
            ydl_opts['force_keyframes_at_cuts'] = True

        format_spec = self.QUALITY_FORMAT_MAP.get(quality, "bestvideo+bestaudio/best")

        if format_type.startswith("MP4"):
            ydl_opts['format'] = format_spec
            ydl_opts['merge_output_format'] = 'mp4'
            ydl_opts['postprocessor_args'] = {
                'merger': ['-c:v', 'copy', '-c:a', 'aac', '-movflags', '+faststart'],
                'VideoConvertor': ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart'],
            }
        elif format_type.startswith("MKV"):
            ydl_opts['format'] = format_spec
            ydl_opts['merge_output_format'] = 'mkv'
        elif format_type.startswith("WEBM"):
            ydl_opts['format'] = 'bestvideo[ext=webm]+bestaudio[ext=webm]/bestvideo+bestaudio/best'
            ydl_opts['merge_output_format'] = 'webm'
        elif format_type.startswith("MP3"):
            bitrate = self.AUDIO_BITRATE_MAP.get(quality, "320")
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': bitrate,
                }
            ]
        elif format_type.startswith("WAV"):
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                }
            ]
        else:
            ydl_opts['format'] = format_spec
            ydl_opts['merge_output_format'] = 'mp4'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            status_callback("İndirme başlatılıyor...", "downloading")
            info = ydl.extract_info(url, download=True)
            
            target_path = None
            if self.last_downloaded_file and os.path.exists(self.last_downloaded_file):
                target_path = self.last_downloaded_file
            elif info:
                candidate = ydl.prepare_filename(info)
                if format_type.startswith("MP3"):
                    base_name, _ = os.path.splitext(candidate)
                    candidate = base_name + ".mp3"
                elif format_type.startswith("WAV"):
                    base_name, _ = os.path.splitext(candidate)
                    candidate = base_name + ".wav"
                elif format_type.startswith("MKV"):
                    base_name, _ = os.path.splitext(candidate)
                    candidate = base_name + ".mkv"
                elif format_type.startswith("WEBM"):
                    base_name, _ = os.path.splitext(candidate)
                    candidate = base_name + ".webm"
                elif format_type.startswith("MP4"):
                    base_name, _ = os.path.splitext(candidate)
                    candidate = base_name + ".mp4"
                if os.path.exists(candidate):
                    target_path = candidate

            self.last_downloaded_file = target_path
            return target_path


class ModernDownloaderApp(ctk.CTk):
    """Apple macOS / iOS Titanium Gray tasarımına sahip premium masaüstü uygulaması."""

    def __init__(self):
        super().__init__()

        self.title("Media Downloader")
        self.geometry("820x790")
        self.minsize(780, 720)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.configure(fg_color=("#f5f5f7", "#1c1c1e"))

        self.engine = DownloaderEngine()
        self.download_thread: Optional[threading.Thread] = None
        self.info_thread: Optional[threading.Thread] = None
        self.current_downloaded_file: Optional[str] = None
        self.current_video_duration: float = 388.0
        self.default_downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")

        self._build_ui()
        self._check_ffmpeg_status()

    def _build_ui(self):
        """Apple macOS standartlarında zarif ve orantılı arayüz yapısını kurar."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header_frame = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=("#ffffff", "#242426"),
            border_width=1,
            border_color=("#e5e5ea", "#323236")
        )
        self.header_frame.grid(row=0, column=0, padx=18, pady=(14, 8), sticky="ew")
        self.header_frame.grid_columnconfigure(1, weight=1)

        mac_dots_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        mac_dots_frame.grid(row=0, column=0, padx=(14, 8), pady=10, sticky="w")

        dot_red = ctk.CTkLabel(mac_dots_frame, text="●", text_color="#ff5f56", font=ctk.CTkFont(size=13))
        dot_red.pack(side="left", padx=2)
        dot_yellow = ctk.CTkLabel(mac_dots_frame, text="●", text_color="#ffbd2e", font=ctk.CTkFont(size=13))
        dot_yellow.pack(side="left", padx=2)
        dot_green = ctk.CTkLabel(mac_dots_frame, text="●", text_color="#27c93f", font=ctk.CTkFont(size=13))
        dot_green.pack(side="left", padx=2)

        header_title_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        header_title_frame.grid(row=0, column=1, padx=6, pady=8, sticky="w")

        self.title_label = ctk.CTkLabel(
            header_title_frame,
            text="Media Downloader",
            font=ctk.CTkFont(family="SF Pro Display", size=16, weight="bold"),
            text_color=("#1d1d1f", "#f5f5f7")
        )
        self.title_label.pack(anchor="w")

        self.supported_label = ctk.CTkLabel(
            header_title_frame,
            text="YouTube • TikTok • Instagram • X • Twitch • Web",
            font=ctk.CTkFont(family="SF Pro Text", size=11),
            text_color=("#86868b", "#98989d")
        )
        self.supported_label.pack(anchor="w")

        header_right_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        header_right_frame.grid(row=0, column=2, padx=14, pady=8, sticky="e")

        self.ffmpeg_badge = ctk.CTkLabel(
            header_right_frame,
            text="● FFmpeg",
            font=ctk.CTkFont(family="SF Pro Text", size=11, weight="bold"),
            fg_color=("#f2f2f7", "#2c2c30"),
            text_color="#30d158",
            corner_radius=10,
            padx=8,
            pady=3
        )
        self.ffmpeg_badge.pack(side="right", padx=(8, 0))

        self.theme_switch = ctk.CTkOptionMenu(
            header_right_frame,
            values=["Koyu Tema", "Açık Tema", "Sistem"],
            command=self._change_theme,
            width=100,
            height=26,
            corner_radius=13,
            fg_color=("#f2f2f7", "#2c2c30"),
            button_color=("#e5e5ea", "#38383c"),
            button_hover_color=("#d1d1d6", "#48484e"),
            text_color=("#1d1d1f", "#f5f5f7"),
            font=ctk.CTkFont(family="SF Pro Text", size=11)
        )
        self.theme_switch.set("Koyu Tema")
        self.theme_switch.pack(side="right")

        self.scrollable_container = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color="transparent"
        )
        self.scrollable_container.grid(row=1, column=0, padx=18, pady=2, sticky="nsew")
        self.scrollable_container.grid_columnconfigure(0, weight=1)

        self._build_url_section(self.scrollable_container)
        self._build_preview_section(self.scrollable_container)
        self._build_options_section(self.scrollable_container)
        self._build_trim_section(self.scrollable_container)

        self.bottom_control_frame = ctk.CTkFrame(
            self,
            corner_radius=12,
            fg_color=("#ffffff", "#242426"),
            border_width=1,
            border_color=("#e5e5ea", "#323236")
        )
        self.bottom_control_frame.grid(row=2, column=0, padx=18, pady=(6, 14), sticky="ew")
        self.bottom_control_frame.grid_columnconfigure(0, weight=1)

        self._build_progress_section(self.bottom_control_frame)

    def _build_url_section(self, parent):
        """Spotlight tarzı modern arama ve URL giriş çubuğu."""
        url_card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=("#ffffff", "#242426"),
            border_width=1,
            border_color=("#e5e5ea", "#323236")
        )
        url_card.grid(row=0, column=0, padx=2, pady=4, sticky="ew")
        url_card.grid_columnconfigure(0, weight=1)

        input_row = ctk.CTkFrame(url_card, fg_color="transparent")
        input_row.grid(row=0, column=0, padx=12, pady=10, sticky="ew")
        input_row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Video veya ses bağlantısı yapıştırın...",
            height=36,
            corner_radius=8,
            fg_color=("#f2f2f7", "#2c2c30"),
            border_color=("#e5e5ea", "#38383c"),
            text_color=("#1d1d1f", "#f5f5f7"),
            font=ctk.CTkFont(family="SF Pro Text", size=13)
        )
        self.url_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.url_entry.bind("<Return>", lambda event: self._fetch_info_threaded())

        btn_group = ctk.CTkFrame(input_row, fg_color="transparent")
        btn_group.grid(row=0, column=1, sticky="e")

        self.paste_btn = AppleButton(
            btn_group,
            text="Yapıştır",
            width=72,
            height=32,
            corner_radius=8,
            fg_color=("#f2f2f7", "#323236"),
            hover_color=("#e5e5ea", "#3f3f44"),
            text_color=("#1d1d1f", "#f5f5f7"),
            command=self._paste_clipboard
        )
        self.paste_btn.pack(side="left", padx=(0, 5))

        self.clear_btn = AppleButton(
            btn_group,
            text="Temizle",
            width=72,
            height=32,
            corner_radius=8,
            fg_color=("#f2f2f7", "#323236"),
            hover_color=("#e5e5ea", "#3f3f44"),
            text_color=("#86868b", "#98989d"),
            command=self._clear_url
        )
        self.clear_btn.pack(side="left", padx=(0, 5))

        self.fetch_btn = AppleButton(
            btn_group,
            text="Bilgileri Getir",
            width=104,
            height=32,
            corner_radius=8,
            fg_color=("#0071e3", "#0071e3"),
            hover_color=("#005bb5", "#0077ed"),
            text_color="#ffffff",
            command=self._fetch_info_threaded
        )
        self.fetch_btn.pack(side="left")

    def _build_preview_section(self, parent):
        """QuickTime Inspector tarzı medya önizleme ve başlık düzenleme alanı."""
        self.preview_card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=("#ffffff", "#242426"),
            border_width=1,
            border_color=("#e5e5ea", "#323236")
        )
        self.preview_card.grid(row=1, column=0, padx=2, pady=4, sticky="ew")
        self.preview_card.grid_columnconfigure(1, weight=1)

        self.thumbnail_label = ctk.CTkLabel(
            self.preview_card,
            text="Önizleme\nYok",
            width=130,
            height=76,
            fg_color=("#f2f2f7", "#1c1c1e"),
            corner_radius=8,
            text_color=("#86868b", "#636366"),
            font=ctk.CTkFont(family="SF Pro Text", size=11)
        )
        self.thumbnail_label.grid(row=0, column=0, padx=10, pady=10, rowspan=4)

        title_label_hint = ctk.CTkLabel(
            self.preview_card,
            text="Dosya Başlığı (Düzenlenebilir):",
            font=ctk.CTkFont(family="SF Pro Text", size=11, weight="bold"),
            text_color=("#86868b", "#98989d"),
            anchor="w"
        )
        title_label_hint.grid(row=0, column=1, padx=(4, 10), pady=(8, 1), sticky="w")

        self.title_entry = ctk.CTkEntry(
            self.preview_card,
            height=30,
            corner_radius=6,
            fg_color=("#f2f2f7", "#2c2c30"),
            border_color=("#e5e5ea", "#38383c"),
            text_color=("#1d1d1f", "#f5f5f7"),
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold")
        )
        self.title_entry.insert(0, "Bağlantı girildiğinde başlık burada görüntülenecektir.")
        self.title_entry.grid(row=1, column=1, padx=(4, 10), pady=(0, 2), sticky="ew")

        self.preview_uploader = ctk.CTkLabel(
            self.preview_card,
            text="Yükleyici: --",
            font=ctk.CTkFont(family="SF Pro Text", size=11),
            text_color=("#86868b", "#98989d"),
            anchor="w"
        )
        self.preview_uploader.grid(row=2, column=1, padx=(4, 10), pady=1, sticky="w")

        info_meta_row = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        info_meta_row.grid(row=3, column=1, padx=(4, 10), pady=(2, 10), sticky="w")

        self.preview_duration = ctk.CTkLabel(
            info_meta_row,
            text="⏱️ --:--",
            font=ctk.CTkFont(family="SF Pro Text", size=11, weight="bold"),
            fg_color=("#f2f2f7", "#2c2c30"),
            corner_radius=6,
            padx=8,
            pady=2,
            text_color=("#1d1d1f", "#f5f5f7")
        )
        self.preview_duration.pack(side="left", padx=(0, 6))

        self.preview_platform = ctk.CTkLabel(
            info_meta_row,
            text="🌐 Web",
            font=ctk.CTkFont(family="SF Pro Text", size=11, weight="bold"),
            fg_color=("#f2f2f7", "#2c2c30"),
            corner_radius=6,
            padx=8,
            pady=2,
            text_color=("#1d1d1f", "#f5f5f7")
        )
        self.preview_platform.pack(side="left")

    def _build_options_section(self, parent):
        """Format, kalite ve hedef klasör ayarları."""
        options_card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=("#ffffff", "#242426"),
            border_width=1,
            border_color=("#e5e5ea", "#323236")
        )
        options_card.grid(row=2, column=0, padx=2, pady=4, sticky="ew")
        options_card.grid_columnconfigure((0, 1), weight=1)

        format_box = ctk.CTkFrame(options_card, fg_color="transparent")
        format_box.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")
        
        format_title = ctk.CTkLabel(
            format_box,
            text="Format",
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
            text_color=("#1d1d1f", "#f5f5f7")
        )
        format_title.pack(anchor="w", pady=(0, 3))

        self.format_segmented = ctk.CTkSegmentedButton(
            format_box,
            values=["MP4", "MKV", "WEBM", "MP3", "WAV"],
            command=self._on_format_changed,
            height=30,
            corner_radius=8,
            fg_color=("#f2f2f7", "#2c2c30"),
            selected_color=("#0071e3", "#0071e3"),
            selected_hover_color=("#005bb5", "#0077ed"),
            unselected_color=("#f2f2f7", "#2c2c30"),
            unselected_hover_color=("#e5e5ea", "#38383c"),
            font=ctk.CTkFont(family="SF Pro Text", size=11, weight="bold")
        )
        self.format_segmented.set("MP4")
        self.format_segmented.pack(fill="x")

        quality_box = ctk.CTkFrame(options_card, fg_color="transparent")
        quality_box.grid(row=0, column=1, padx=12, pady=(10, 4), sticky="ew")

        self.quality_title = ctk.CTkLabel(
            quality_box,
            text="Kalite",
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
            text_color=("#1d1d1f", "#f5f5f7")
        )
        self.quality_title.pack(anchor="w", pady=(0, 3))

        self.quality_option = ctk.CTkOptionMenu(
            quality_box,
            values=list(DownloaderEngine.QUALITY_FORMAT_MAP.keys()),
            height=30,
            corner_radius=8,
            fg_color=("#f2f2f7", "#2c2c30"),
            button_color=("#e5e5ea", "#38383c"),
            button_hover_color=("#d1d1d6", "#48484e"),
            text_color=("#1d1d1f", "#f5f5f7"),
            font=ctk.CTkFont(family="SF Pro Text", size=12)
        )
        self.quality_option.set("En Yüksek (Best)")
        self.quality_option.pack(fill="x")

        dir_box = ctk.CTkFrame(options_card, fg_color="transparent")
        dir_box.grid(row=1, column=0, columnspan=2, padx=12, pady=(4, 10), sticky="ew")
        dir_box.grid_columnconfigure(0, weight=1)

        dir_title = ctk.CTkLabel(
            dir_box,
            text="Kayıt Konumu",
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
            text_color=("#1d1d1f", "#f5f5f7")
        )
        dir_title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 3))

        self.dir_entry = ctk.CTkEntry(
            dir_box,
            height=32,
            corner_radius=8,
            fg_color=("#f2f2f7", "#2c2c30"),
            border_color=("#e5e5ea", "#38383c"),
            text_color=("#1d1d1f", "#f5f5f7"),
            font=ctk.CTkFont(family="SF Pro Text", size=12)
        )
        self.dir_entry.insert(0, self.default_downloads_dir)
        self.dir_entry.grid(row=1, column=0, padx=(0, 6), sticky="ew")

        self.browse_btn = AppleButton(
            dir_box,
            text="Seç...",
            width=70,
            height=32,
            corner_radius=8,
            fg_color=("#f2f2f7", "#323236"),
            hover_color=("#e5e5ea", "#3f3f44"),
            text_color=("#1d1d1f", "#f5f5f7"),
            command=self._browse_directory
        )
        self.browse_btn.grid(row=1, column=1, padx=(0, 5))

        self.open_dir_btn = AppleButton(
            dir_box,
            text="Klasör",
            width=70,
            height=32,
            corner_radius=8,
            fg_color=("#f2f2f7", "#323236"),
            hover_color=("#e5e5ea", "#3f3f44"),
            text_color=("#86868b", "#98989d"),
            command=self._open_current_directory
        )
        self.open_dir_btn.grid(row=1, column=2)

    def _build_trim_section(self, parent):
        """Apple Final Cut tarzı kırpma ve çift tutamaçlı kaydırıcı alanı."""
        trim_card = ctk.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=("#ffffff", "#242426"),
            border_width=1,
            border_color=("#e5e5ea", "#323236")
        )
        trim_card.grid(row=3, column=0, padx=2, pady=4, sticky="ew")
        trim_card.grid_columnconfigure(0, weight=1)

        card_title = ctk.CTkLabel(
            trim_card,
            text="Kırpma / Zaman Aralığı",
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
            text_color=("#1d1d1f", "#f5f5f7"),
            anchor="w"
        )
        card_title.grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")

        self.trim_container = ctk.CTkFrame(trim_card, fg_color="transparent")
        self.trim_container.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="ew")
        self.trim_container.grid_columnconfigure(0, weight=1)

        self.range_slider = CTkRangeSlider(
            self.trim_container,
            from_=0.0,
            to=self.current_video_duration,
            start_val=0.0,
            end_val=self.current_video_duration,
            command=self._on_slider_values_changed,
            height=34
        )
        self.range_slider.pack(fill="x", pady=(2, 4))

        time_boxes_frame = ctk.CTkFrame(self.trim_container, fg_color="transparent")
        time_boxes_frame.pack(fill="x", pady=(0, 4))
        time_boxes_frame.grid_columnconfigure(1, weight=1)

        self.start_time_entry = ctk.CTkEntry(
            time_boxes_frame,
            width=92,
            height=30,
            corner_radius=6,
            justify="center",
            fg_color=("#f2f2f7", "#2c2c30"),
            border_color=("#e5e5ea", "#38383c"),
            text_color=("#1d1d1f", "#f5f5f7"),
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold")
        )
        self.start_time_entry.insert(0, "00:00:00")
        self.start_time_entry.grid(row=0, column=0, sticky="w")
        self.start_time_entry.bind("<Return>", lambda e: self._on_time_entries_edited())
        self.start_time_entry.bind("<FocusOut>", lambda e: self._on_time_entries_edited())

        self.trim_summary_label = ctk.CTkLabel(
            time_boxes_frame,
            text="00:06:28",
            font=ctk.CTkFont(family="SF Pro Text", size=11, weight="bold"),
            text_color=("#86868b", "#98989d")
        )
        self.trim_summary_label.grid(row=0, column=1, sticky="nsew")

        self.end_time_entry = ctk.CTkEntry(
            time_boxes_frame,
            width=92,
            height=30,
            corner_radius=6,
            justify="center",
            fg_color=("#f2f2f7", "#2c2c30"),
            border_color=("#e5e5ea", "#38383c"),
            text_color=("#1d1d1f", "#f5f5f7"),
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold")
        )
        self.end_time_entry.insert(0, TimeParser.format_duration(self.current_video_duration, force_hours=True))
        self.end_time_entry.grid(row=0, column=2, sticky="e")
        self.end_time_entry.bind("<Return>", lambda e: self._on_time_entries_edited())
        self.end_time_entry.bind("<FocusOut>", lambda e: self._on_time_entries_edited())

    def _build_progress_section(self, parent):
        """Minimalist durum barı, ince ilerleme çubuğu ve merkezlenmiş buton alanı."""
        status_row = ctk.CTkFrame(parent, fg_color="transparent")
        status_row.grid(row=0, column=0, padx=14, pady=(8, 2), sticky="ew")
        status_row.grid_columnconfigure(0, weight=1)

        self.status_banner = ctk.CTkLabel(
            status_row,
            text="Hazır",
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
            text_color=("#86868b", "#98989d"),
            anchor="w"
        )
        self.status_banner.grid(row=0, column=0, sticky="w")

        self.percent_label = ctk.CTkLabel(
            status_row,
            text="%0",
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
            text_color=("#1d1d1f", "#f5f5f7"),
            anchor="e"
        )
        self.percent_label.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(
            parent,
            height=6,
            corner_radius=3,
            fg_color=("#e5e5ea", "#2c2c30"),
            progress_color=("#0071e3", "#0071e3")
        )
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=1, column=0, padx=14, pady=(2, 6), sticky="ew")

        metrics_frame = ctk.CTkFrame(parent, fg_color="transparent")
        metrics_frame.grid(row=2, column=0, padx=14, pady=(0, 8), sticky="ew")
        metrics_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.speed_label = ctk.CTkLabel(
            metrics_frame,
            text="Hız: --",
            font=ctk.CTkFont(family="SF Pro Text", size=11),
            text_color=("#86868b", "#6e6e73"),
            anchor="w"
        )
        self.speed_label.grid(row=0, column=0, sticky="w")

        self.size_label = ctk.CTkLabel(
            metrics_frame,
            text="0 MB / 0 MB",
            font=ctk.CTkFont(family="SF Pro Text", size=11),
            text_color=("#86868b", "#6e6e73"),
            anchor="center"
        )
        self.size_label.grid(row=0, column=1, sticky="ew")

        self.eta_label = ctk.CTkLabel(
            metrics_frame,
            text="Kalan: --:--",
            font=ctk.CTkFont(family="SF Pro Text", size=11),
            text_color=("#86868b", "#6e6e73"),
            anchor="e"
        )
        self.eta_label.grid(row=0, column=2, sticky="e")

        action_center_frame = ctk.CTkFrame(parent, fg_color="transparent")
        action_center_frame.grid(row=3, column=0, padx=14, pady=(2, 10))

        self.download_btn = AppleButton(
            action_center_frame,
            text="İndirmeyi Başlat",
            width=190,
            height=36,
            corner_radius=18,
            fg_color=("#0071e3", "#0071e3"),
            hover_color=("#005bb5", "#0077ed"),
            font=ctk.CTkFont(family="SF Pro Text", size=13, weight="bold"),
            command=self._start_or_cancel_download
        )
        self.download_btn.pack(side="left", padx=4)

        self.show_file_btn = AppleButton(
            action_center_frame,
            text="Klasörde Göster",
            width=130,
            height=36,
            corner_radius=18,
            fg_color=("#f2f2f7", "#323236"),
            hover_color=("#e5e5ea", "#3f3f44"),
            text_color=("#1d1d1f", "#f5f5f7"),
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
            command=self._reveal_downloaded_file
        )

        self.open_file_btn = AppleButton(
            action_center_frame,
            text="Dosyayı Aç",
            width=110,
            height=36,
            corner_radius=18,
            fg_color=("#f2f2f7", "#323236"),
            hover_color=("#e5e5ea", "#3f3f44"),
            text_color=("#1d1d1f", "#f5f5f7"),
            font=ctk.CTkFont(family="SF Pro Text", size=12, weight="bold"),
            command=self._open_downloaded_file
        )

    def _check_ffmpeg_status(self):
        """FFmpeg durumunu kontrol eder ve Apple tarzı rozeti günceller."""
        ffmpeg_path = FFmpegHelper.get_ffmpeg_path()
        if ffmpeg_path:
            self.ffmpeg_badge.configure(
                text="● FFmpeg",
                text_color="#30d158"
            )
        else:
            self.ffmpeg_badge.configure(
                text="● FFmpeg Yok",
                text_color="#ff9f0a"
            )

    def _change_theme(self, theme_choice: str):
        if theme_choice == "Koyu Tema":
            ctk.set_appearance_mode("dark")
        elif theme_choice == "Açık Tema":
            ctk.set_appearance_mode("light")
        else:
            ctk.set_appearance_mode("system")
        self.after(10, self.range_slider._draw_slider)

    def _on_format_changed(self, selected_format: str):
        """Format değiştiğinde kalite seçeneklerini günceller."""
        if selected_format in ["MP3", "WAV"]:
            self.quality_title.configure(text="Ses Kalitesi (Bitrate)")
            options = list(DownloaderEngine.AUDIO_BITRATE_MAP.keys())
            self.quality_option.configure(values=options)
            self.quality_option.set("320 kbps (En Yüksek)")
        else:
            self.quality_title.configure(text="Kalite")
            options = list(DownloaderEngine.QUALITY_FORMAT_MAP.keys())
            self.quality_option.configure(values=options)
            self.quality_option.set("En Yüksek (Best)")

    def _on_slider_values_changed(self, start_val: float, end_val: float):
        start_str = TimeParser.format_duration(start_val, force_hours=True)
        end_str = TimeParser.format_duration(end_val, force_hours=True)

        self.start_time_entry.delete(0, "end")
        self.start_time_entry.insert(0, start_str)

        self.end_time_entry.delete(0, "end")
        self.end_time_entry.insert(0, end_str)

        diff = max(0.0, end_val - start_val)
        diff_str = TimeParser.format_duration(diff, force_hours=True)
        self.trim_summary_label.configure(text=f"{diff_str}")

    def _on_time_entries_edited(self):
        try:
            start_str = self.start_time_entry.get().strip()
            end_str = self.end_time_entry.get().strip()

            st = TimeParser.parse_time(start_str) or 0.0
            et = TimeParser.parse_time(end_str) or self.current_video_duration

            if et <= st:
                et = st + 1.0

            if et > self.range_slider.to:
                self.range_slider.set_range(0.0, et)
                self.current_video_duration = et

            self.range_slider.set_values(st, et, trigger_callback=False)
            diff = max(0.0, et - st)
            self.trim_summary_label.configure(text=f"{TimeParser.format_duration(diff, force_hours=True)}")
        except Exception:
            pass

    def _paste_clipboard(self):
        try:
            clipboard_text = self.clipboard_get()
            if clipboard_text:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, clipboard_text.strip())
                self._fetch_info_threaded()
        except Exception:
            pass

    def _clear_url(self):
        self.url_entry.delete(0, "end")
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, "Bağlantı girildiğinde başlık burada görüntülenecektir.")
        self.preview_uploader.configure(text="Yükleyici: --")
        self.preview_duration.configure(text="⏱️ --:--")
        self.preview_platform.configure(text="🌐 Web")
        self.thumbnail_label.configure(image=None, text="Önizleme\nYok")
        self.current_video_duration = 388.0
        self.range_slider.set_range(0.0, self.current_video_duration, reset_values=True)
        self._on_slider_values_changed(0.0, self.current_video_duration)

    def _browse_directory(self):
        selected_dir = ctk.filedialog.askdirectory(initialdir=self.dir_entry.get())
        if selected_dir:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, selected_dir)

    def _open_current_directory(self):
        raw_dir = self.dir_entry.get().strip()
        target_dir = os.path.abspath(os.path.normpath(raw_dir))
        if os.path.exists(target_dir):
            if sys.platform == 'win32':
                subprocess.run(f'explorer "{target_dir}"', shell=True)
            elif sys.platform == 'darwin':
                subprocess.run(['open', target_dir])
            else:
                subprocess.run(['xdg-open', target_dir])

    def _fetch_info_threaded(self):
        url = self.url_entry.get().strip()
        if not url:
            self._set_status("Lütfen bir bağlantı girin.", "error")
            return

        if self.info_thread and self.info_thread.is_alive():
            return

        self.fetch_btn.configure(state="disabled", text="Alınıyor...")
        self._set_status("Medya bilgileri alınıyor...", "info")

        def worker():
            try:
                info = self.engine.fetch_info(url)
                self.after(0, lambda: self._on_info_fetched_success(info))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: self._on_info_fetched_error(err_msg))

        self.info_thread = threading.Thread(target=worker, daemon=True)
        self.info_thread.start()

    def _on_info_fetched_success(self, info: Dict[str, Any]):
        self.fetch_btn.configure(state="normal", text="Bilgileri Getir")
        
        title = info.get('title', 'Bilinmeyen Başlık')
        uploader = info.get('uploader') or info.get('channel') or info.get('creator') or 'Bilinmiyor'
        duration = info.get('duration')
        extractor = info.get('extractor_key') or info.get('extractor') or 'Web'
        thumbnail_url = info.get('thumbnail')

        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, title)

        self.preview_uploader.configure(text=f"Yükleyici: {uploader}")
        self.preview_duration.configure(text=f"⏱️ {TimeParser.format_duration(duration, force_hours=False)}")
        self.preview_platform.configure(text=f"🌐 {extractor.capitalize()}")
        self._set_status("Medya bilgileri hazır.", "success")

        if duration and duration > 0:
            self.current_video_duration = float(duration)
            self.range_slider.set_range(0.0, self.current_video_duration, reset_values=True)
            self._on_slider_values_changed(0.0, self.current_video_duration)

        if thumbnail_url:
            threading.Thread(target=self._load_thumbnail_async, args=(thumbnail_url,), daemon=True).start()

    def _load_thumbnail_async(self, thumbnail_url: str):
        try:
            req = urllib.request.Request(
                thumbnail_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=8) as response:
                image_data = response.read()
            pil_image = Image.open(BytesIO(image_data))
            pil_image = pil_image.resize((130, 76), Image.Resampling.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(130, 76))
            self.after(0, lambda: self.thumbnail_label.configure(image=ctk_img, text=""))
        except Exception:
            pass

    def _on_info_fetched_error(self, err_msg: str):
        self.fetch_btn.configure(state="normal", text="Bilgileri Getir")
        short_err = err_msg.split('\n')[0] if err_msg else "Bilinmeyen hata"
        self._set_status(f"Hata: {short_err}", "error")

    def _start_or_cancel_download(self):
        if self.download_thread and self.download_thread.is_alive():
            self.engine.cancel()
            self._set_status("İptal ediliyor...", "warning")
            self.download_btn.configure(state="disabled", text="İptal Ediliyor...")
            return

        url = self.url_entry.get().strip()
        if not url:
            self._set_status("Lütfen geçerli bir URL girin.", "error")
            return

        output_dir = self.dir_entry.get().strip()
        if not output_dir:
            self._set_status("Lütfen kayıt klasörü seçin.", "error")
            return

        format_type = self.format_segmented.get()
        quality = self.quality_option.get()
        custom_title = self.title_entry.get().strip()

        st_val, et_val = self.range_slider.get_values()
        max_dur = self.range_slider.to
        is_trimmed = (st_val > 0.5) or (et_val < (max_dur - 0.5))

        start_sec = None
        end_sec = None
        if is_trimmed:
            start_sec = st_val
            end_sec = et_val
            if end_sec <= start_sec:
                self._set_status("Hata: Bitiş süresi başlangıçtan büyük olmalıdır.", "error")
                return

        self._reset_progress()
        self.show_file_btn.pack_forget()
        self.open_file_btn.pack_forget()
        self.download_btn.configure(
            text="İptal Et",
            fg_color=("#ff3b30", "#ff453a"),
            hover_color=("#d70015", "#d73329")
        )

        def worker():
            try:
                final_file = self.engine.download(
                    url=url,
                    output_dir=output_dir,
                    format_type=format_type,
                    quality=quality,
                    custom_title=custom_title,
                    trim_enabled=is_trimmed,
                    start_time_sec=start_sec,
                    end_time_sec=end_sec,
                    progress_callback=lambda p: self.after(0, lambda: self._update_progress_ui(p)),
                    status_callback=lambda s, t: self.after(0, lambda: self._set_status(s, t)),
                )
                self.after(0, lambda: self._on_download_finished_success(final_file))
            except yt_dlp.utils.DownloadCancelled:
                self.after(0, self._on_download_cancelled)
            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._on_download_finished_error(err))

        self.download_thread = threading.Thread(target=worker, daemon=True)
        self.download_thread.start()

    def _update_progress_ui(self, p: Dict[str, Any]):
        percent = p.get('percent', 0.0)
        fraction = min(max(percent / 100.0, 0.0), 1.0)
        self.progress_bar.set(fraction)

        self.percent_label.configure(text=f"%{percent:.1f}")
        
        speed = p.get('speed')
        self.speed_label.configure(text=f"Hız: {TimeParser.format_speed(speed)}")

        downloaded = p.get('downloaded_bytes', 0)
        total = p.get('total_bytes', 0)
        self.size_label.configure(text=f"{TimeParser.format_bytes(downloaded)} / {TimeParser.format_bytes(total)}")

        eta = p.get('eta')
        self.eta_label.configure(text=f"Kalan: {TimeParser.format_duration(eta, force_hours=False)}")

        self._set_status(f"İndiriliyor: %{percent:.1f}", "downloading")

    def _on_download_finished_success(self, filepath: Optional[str]):
        self._reset_download_button()
        self.progress_bar.set(1.0)
        self.percent_label.configure(text="%100")
        self.eta_label.configure(text="Kalan: 00:00")
        self.current_downloaded_file = filepath
        self._set_status("Tamamlandı", "success")
        self.show_file_btn.pack(side="left", padx=4)
        self.open_file_btn.pack(side="left", padx=4)

    def _on_download_cancelled(self):
        self._reset_download_button()
        self._set_status("İptal edildi", "warning")

    def _on_download_finished_error(self, err_msg: str):
        self._reset_download_button()
        short_err = err_msg.split('\n')[0] if err_msg else "Bilinmeyen hata"
        self._set_status(f"Hata: {short_err}", "error")

    def _reset_download_button(self):
        self.download_btn.configure(
            state="normal",
            text="İndirmeyi Başlat",
            fg_color=("#0071e3", "#0071e3"),
            hover_color=("#005bb5", "#0077ed")
        )

    def _reset_progress(self):
        self.progress_bar.set(0.0)
        self.percent_label.configure(text="%0")
        self.speed_label.configure(text="Hız: --")
        self.size_label.configure(text="0 MB / 0 MB")
        self.eta_label.configure(text="Kalan: --:--")

    def _set_status(self, text: str, status_type: str = "info"):
        color_map = {
            "info": ("#86868b", "#98989d"),
            "downloading": ("#0071e3", "#0071e3"),
            "processing": ("#ff9500", "#ff9f0a"),
            "success": ("#34c759", "#30d158"),
            "warning": ("#ff9500", "#ff9f0a"),
            "error": ("#ff3b30", "#ff453a"),
        }
        text_color = color_map.get(status_type, ("#86868b", "#98989d"))
        self.status_banner.configure(text=text, text_color=text_color)

    def _reveal_downloaded_file(self):
        if self.current_downloaded_file and os.path.exists(self.current_downloaded_file):
            target = os.path.abspath(os.path.normpath(self.current_downloaded_file))
            if sys.platform == 'win32':
                subprocess.run(f'explorer /select,"{target}"', shell=True)
            elif sys.platform == 'darwin':
                subprocess.run(['open', '-R', target])
            else:
                subprocess.run(['xdg-open', os.path.dirname(target)])
        else:
            self._open_current_directory()

    def _open_downloaded_file(self):
        if self.current_downloaded_file and os.path.exists(self.current_downloaded_file):
            target = os.path.abspath(os.path.normpath(self.current_downloaded_file))
            if sys.platform == 'win32':
                os.startfile(target)
            elif sys.platform == 'darwin':
                subprocess.run(['open', target])
            else:
                subprocess.run(['xdg-open', target])


if __name__ == "__main__":
    app = ModernDownloaderApp()
    app.mainloop()
