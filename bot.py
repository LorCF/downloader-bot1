import os
import sys
import re
import json
import shutil
import tempfile
import threading
from typing import Optional, Dict, Any, Tuple

import telebot
from telebot import types
import yt_dlp

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_config.json")
TEMP_DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_downloads")


class TimeParser:
    @staticmethod
    def parse_time(time_str: str) -> Optional[float]:
        if not time_str or not time_str.strip():
            return None
        time_str = time_str.strip()
        parts = time_str.split(":")
        try:
            if len(parts) == 1:
                val = float(parts[0])
                return max(0.0, val)
            elif len(parts) == 2:
                mins = float(parts[0])
                secs = float(parts[1])
                return max(0.0, mins * 60 + secs)
            elif len(parts) == 3:
                hrs = float(parts[0])
                mins = float(parts[1])
                secs = float(parts[2])
                return max(0.0, hrs * 3600 + mins * 60 + secs)
            return None
        except ValueError:
            return None

    @staticmethod
    def format_duration(seconds: Optional[float]) -> str:
        if seconds is None or seconds < 0:
            return "--:--"
        total_secs = int(round(seconds))
        hours, remainder = divmod(total_secs, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"


class FFmpegHelper:
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
            os.path.join(base_dir, "ffmpeg", "bin", "ffmpeg.exe"),
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


def get_cookie_file_path() -> Optional[str]:
    cookies_content = os.environ.get("COOKIES_CONTENT", "").strip()
    if cookies_content:
        path = os.path.join(tempfile.gettempdir(), "ytdlp_cookies.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(cookies_content)
            return path
        except Exception:
            pass

    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_candidates = [
        os.path.join(base_dir, "cookies.txt"),
        os.path.join(os.getcwd(), "cookies.txt"),
    ]
    for cand in local_candidates:
        if os.path.exists(cand):
            return cand

    return None


def load_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                token = data.get("bot_token", "").strip()
                if token:
                    return token
        except Exception:
            pass

    print("=" * 60)
    print("🤖 TELEGRAM BOT KURULUMU")
    print("=" * 60)
    token = input("Bot Token'ı buraya yapıştır ve Enter'a bas: ").strip()
    if token:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"bot_token": token}, f, indent=4)
        return token

    sys.exit(1)


def start_health_server():
    port_str = os.environ.get("PORT")
    if not port_str:
        return
    try:
        from http.server import HTTPServer, BaseHTTPRequestHandler

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Bot is alive and running!")

            def log_message(self, format, *args):
                pass

        port = int(port_str)
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"🌐 Cloud Health Check sunucusu port {port} üzerinde başlatıldı.")
    except Exception as e:
        print(f"Health server başlatılamadı: {e}")


def extract_first_url(text: str) -> Optional[str]:
    url_pattern = r"(https?://[^\s]+)"
    match = re.search(url_pattern, text)
    if match:
        return match.group(1).strip()
    return None


def get_media_info(url: str) -> Dict[str, Any]:
    ffmpeg_exe = FFmpegHelper.get_ffmpeg_path()
    cookie_path = get_cookie_file_path()
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        },
    }
    if ffmpeg_exe:
        ydl_opts["ffmpeg_location"] = ffmpeg_exe
    if cookie_path:
        ydl_opts["cookiefile"] = cookie_path

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


FORMATS = ["MP4", "MKV", "WEBM", "MP3", "WAV"]

VIDEO_QUALITIES = [
    "En Yüksek (Best)",
    "1080p (Full HD)",
    "720p (HD)",
    "480p (SD)",
    "360p (Düşük)",
]

AUDIO_QUALITIES = [
    "320 kbps (En Yüksek)",
    "256 kbps (Yüksek)",
    "192 kbps (Standart)",
    "128 kbps (Düşük)",
]

QUALITY_FORMAT_MAP = {
    "En Yüksek (Best)": "bestvideo+bestaudio/best",
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
}

user_sessions: Dict[str, Dict[str, Any]] = {}
sessions_lock = threading.Lock()


def build_studio_card(session: Dict[str, Any]) -> Tuple[str, types.InlineKeyboardMarkup]:
    title = session.get("custom_title") or session.get("title", "Medya")
    clean_title = (title[:70] + "...") if len(title) > 70 else title
    uploader = session.get("uploader", "Bilinmiyor")
    duration_str = TimeParser.format_duration(session.get("duration"))

    fmt = session.get("format", "MP4")
    quality = session.get("quality", "En Yüksek (Best)")
    trim_enabled = session.get("trim_enabled", False)
    start_t = session.get("start_time", 0.0)
    end_t = session.get("end_time")

    if trim_enabled and end_t is not None:
        trim_str = f"✂️ <b>Aktif</b> ({TimeParser.format_duration(start_t)} - {TimeParser.format_duration(end_t)})"
    else:
        trim_str = "Kapalı (Tüm Süre)"

    text = (
        f"⚡ <b>Media Downloader & Studio</b>\n\n"
        f"🎬 <b>{clean_title}</b>\n"
        f"👤 <b>Yükleyici:</b> {uploader} | ⏱️ <b>Süre:</b> {duration_str}\n"
        f"────────────────────────\n"
        f"📦 <b>Format:</b> <code>{fmt}</code>\n"
        f"💎 <b>Kalite:</b> <code>{quality}</code>\n"
        f"✂️ <b>Kırpma:</b> {trim_str}\n"
        f"────────────────────────\n"
        f"Aşağıdan ayarları düzenleyebilir veya indirmeyi başlatabilirsiniz:"
    )

    markup = types.InlineKeyboardMarkup()

    fmt_buttons = []
    for f in FORMATS:
        label = f"✓ {f}" if f == fmt else f
        fmt_buttons.append(
            types.InlineKeyboardButton(label, callback_data=f"set_fmt:{session['id']}:{f}")
        )
    markup.row(*fmt_buttons[:3])
    markup.row(*fmt_buttons[3:])

    q_label = f"💎 Kalite: {quality}"
    markup.row(types.InlineKeyboardButton(q_label, callback_data=f"menu_q:{session['id']}"))

    btn_trim = types.InlineKeyboardButton(
        "✂️ Kırpma Aralığı Belirle", callback_data=f"menu_trim:{session['id']}"
    )
    btn_rename = types.InlineKeyboardButton(
        "✏️ Başlığı Değiştir", callback_data=f"menu_rename:{session['id']}"
    )
    markup.row(btn_trim, btn_rename)

    btn_download = types.InlineKeyboardButton(
        "🚀 İndirmeyi Başlat", callback_data=f"start_dl:{session['id']}"
    )
    markup.row(btn_download)

    btn_new = types.InlineKeyboardButton(
        "🔗 Yeni Link Gir", callback_data="ask_link"
    )
    markup.row(btn_new)

    return text, markup


def download_media_file(session: Dict[str, Any], output_folder: str) -> str:
    url = session["url"]
    fmt = session.get("format", "MP4")
    quality = session.get("quality", "En Yüksek (Best)")
    custom_title = session.get("custom_title") or session.get("title", "Video")
    clean_title = re.sub(r'[\\/*?:"<>|]', "", custom_title).strip() or "Media"

    trim_enabled = session.get("trim_enabled", False)
    start_sec = session.get("start_time", 0.0)
    end_sec = session.get("end_time")

    ffmpeg_exe = FFmpegHelper.get_ffmpeg_path()
    cookie_path = get_cookie_file_path()

    os.makedirs(output_folder, exist_ok=True)
    outtmpl = os.path.join(output_folder, f"{clean_title[:80]}.%(ext)s")

    ydl_opts: Dict[str, Any] = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "overwrites": True,
        "windowsfilenames": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        },
    }

    if ffmpeg_exe:
        ydl_opts["ffmpeg_location"] = ffmpeg_exe
    if cookie_path:
        ydl_opts["cookiefile"] = cookie_path

    if trim_enabled and end_sec is not None and end_sec > start_sec:
        ranges = [(start_sec, end_sec)]
        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(None, ranges)
        ydl_opts["force_keyframes_at_cuts"] = True

    if fmt == "MP4":
        ydl_opts["format"] = QUALITY_FORMAT_MAP.get(quality, "bestvideo+bestaudio/best")
        ydl_opts["merge_output_format"] = "mp4"
        ydl_opts["postprocessor_args"] = {
            "merger": ["-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart"],
        }
    elif fmt == "MKV":
        ydl_opts["format"] = QUALITY_FORMAT_MAP.get(quality, "bestvideo+bestaudio/best")
        ydl_opts["merge_output_format"] = "mkv"
    elif fmt == "WEBM":
        ydl_opts["format"] = "bestvideo[ext=webm]+bestaudio[ext=webm]/best"
        ydl_opts["merge_output_format"] = "webm"
    elif fmt == "MP3":
        bitrate = AUDIO_BITRATE_MAP.get(quality, "320")
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": bitrate,
            }
        ]
    elif fmt == "WAV":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        base, _ = os.path.splitext(filename)

        if fmt == "MP3":
            candidate = f"{base}.mp3"
            if os.path.exists(candidate):
                return candidate
        elif fmt == "WAV":
            candidate = f"{base}.wav"
            if os.path.exists(candidate):
                return candidate
        elif fmt == "MP4":
            candidate = f"{base}.mp4"
            if os.path.exists(candidate):
                return candidate

        if os.path.exists(filename):
            return filename

        for cand in os.listdir(output_folder):
            full_cand = os.path.join(output_folder, cand)
            if os.path.isfile(full_cand):
                return full_cand

        return filename


def main():
    start_health_server()
    token = load_token()
    bot = telebot.TeleBot(token, parse_mode="HTML")
    os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)

    print("\n🚀 Media Downloader & Studio Botu çalışıyor...")

    @bot.message_handler(commands=["start"])
    def cmd_start(message):
        welcome_text = (
            "⚡ <b>Media Downloader & Studio</b>\n"
            "<i>YouTube • TikTok • Instagram • X • Twitch • Web</i>\n\n"
            "Medya indirmek, biçimlendirmek veya kırpmak için aşağıdaki butona tıklayın."
        )
        markup = types.InlineKeyboardMarkup()
        btn_enter_link = types.InlineKeyboardButton(
            "🔗 Link Gir", callback_data="ask_link"
        )
        markup.add(btn_enter_link)
        bot.reply_to(message, welcome_text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "ask_link")
    def cb_ask_link(call):
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "📥 <b>Lütfen video veya ses bağlantısını (URL) buraya yapıştırıp gönderin:</b>",
            reply_markup=types.ForceReply(selective=True),
        )
        bot.register_next_step_handler(msg, process_url_input)

    def process_url_input(message):
        text = message.text or ""
        url = extract_first_url(text)

        if not url:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔗 Tekrar Dene", callback_data="ask_link"))
            bot.reply_to(
                message,
                "⚠️ Geçerli bir bağlantı bulunamadı. Lütfen YouTube, Instagram, TikTok veya desteklenen bir link gönderin.",
                reply_markup=markup,
            )
            return

        status_msg = bot.reply_to(message, "🔍 <i>Medya bilgileri alınıyor, lütfen bekleyin...</i>")

        def fetch_worker():
            try:
                info = get_media_info(url)
                session_id = f"{message.chat.id}_{message.message_id}"
                duration = info.get("duration")

                session_data = {
                    "id": session_id,
                    "chat_id": message.chat.id,
                    "url": url,
                    "title": info.get("title", "Video"),
                    "custom_title": None,
                    "uploader": info.get("uploader") or info.get("channel") or "Bilinmiyor",
                    "duration": duration,
                    "format": "MP4",
                    "quality": "En Yüksek (Best)",
                    "trim_enabled": False,
                    "start_time": 0.0,
                    "end_time": duration,
                }

                with sessions_lock:
                    user_sessions[session_id] = session_data

                card_text, card_markup = build_studio_card(session_data)
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    text=card_text,
                    reply_markup=card_markup,
                )

            except Exception as e:
                err_text = str(e)
                try:
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        text=f"❌ Bilgiler alınamadı:\n<code>{err_text[:250]}</code>",
                    )
                except Exception:
                    pass

        threading.Thread(target=fetch_worker, daemon=True).start()

    @bot.message_handler(func=lambda msg: extract_first_url(msg.text or "") is not None)
    def handle_direct_url(message):
        process_url_input(message)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("set_fmt:"))
    def cb_set_format(call):
        parts = call.data.split(":")
        session_id = parts[1]
        new_fmt = parts[2]

        with sessions_lock:
            session = user_sessions.get(session_id)
            if not session:
                bot.answer_callback_query(call.id, "Oturum süresi dolmuş. Lütfen tekrar link girin.", show_alert=True)
                return

            session["format"] = new_fmt
            if new_fmt in ["MP3", "WAV"]:
                if session["quality"] not in AUDIO_QUALITIES:
                    session["quality"] = "320 kbps (En Yüksek)"
            else:
                if session["quality"] not in VIDEO_QUALITIES:
                    session["quality"] = "En Yüksek (Best)"

            card_text, card_markup = build_studio_card(session)

        bot.answer_callback_query(call.id, f"Format: {new_fmt}")
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=card_text,
                reply_markup=card_markup,
            )
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda call: call.data.startswith("menu_q:"))
    def cb_quality_menu(call):
        session_id = call.data.split(":")[1]
        with sessions_lock:
            session = user_sessions.get(session_id)
            if not session:
                bot.answer_callback_query(call.id, "Oturum süresi dolmuş.", show_alert=True)
                return

            fmt = session.get("format", "MP4")
            current_q = session.get("quality")

        qualities = AUDIO_QUALITIES if fmt in ["MP3", "WAV"] else VIDEO_QUALITIES
        markup = types.InlineKeyboardMarkup(row_width=1)

        for q in qualities:
            prefix = "🔘 " if q == current_q else ""
            markup.add(
                types.InlineKeyboardButton(
                    f"{prefix}{q}", callback_data=f"set_q:{session_id}:{q}"
                )
            )

        markup.add(types.InlineKeyboardButton("🔙 Geri", callback_data=f"back_panel:{session_id}"))

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"💎 <b>{fmt} İçin Kalite Seçin:</b>",
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("set_q:"))
    def cb_set_quality(call):
        parts = call.data.split(":")
        session_id = parts[1]
        new_q = ":".join(parts[2:])

        with sessions_lock:
            session = user_sessions.get(session_id)
            if not session:
                bot.answer_callback_query(call.id, "Oturum süresi dolmuş.", show_alert=True)
                return
            session["quality"] = new_q
            card_text, card_markup = build_studio_card(session)

        bot.answer_callback_query(call.id, f"Kalite: {new_q}")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=card_text,
            reply_markup=card_markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("back_panel:"))
    def cb_back_panel(call):
        session_id = call.data.split(":")[1]
        with sessions_lock:
            session = user_sessions.get(session_id)
            if not session:
                bot.answer_callback_query(call.id, "Oturum süresi dolmuş.", show_alert=True)
                return
            card_text, card_markup = build_studio_card(session)

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=card_text,
            reply_markup=card_markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("menu_trim:"))
    def cb_menu_trim(call):
        session_id = call.data.split(":")[1]
        with sessions_lock:
            session = user_sessions.get(session_id)
            if not session:
                bot.answer_callback_query(call.id, "Oturum süresi dolmuş.", show_alert=True)
                return

        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "✂️ <b>Kırpma Aralığını Girin</b>\n\n"
            "Format: <code>başlangıç - bitiş</code>\n"
            "Örnekler:\n"
            "• <code>00:30 - 02:15</code>\n"
            "• <code>01:20 - 03:00</code>\n"
            "• <code>30 - 90</code> (saniye cinsinden)\n\n"
            "Kırpmayı iptal etmek veya kapatmak için <code>kapat</code> yazın.",
            reply_markup=types.ForceReply(selective=True),
        )

        def process_trim_input(reply_msg):
            reply_text = (reply_msg.text or "").strip().lower()
            with sessions_lock:
                sess = user_sessions.get(session_id)
                if not sess:
                    return

                if reply_text in ["kapat", "iptal", "reset", "0"]:
                    sess["trim_enabled"] = False
                    bot.reply_to(reply_msg, "✂️ Kırpma kapatıldı (Tüm video indirilecek).")
                else:
                    parts = re.split(r"[-–—]", reply_text)
                    if len(parts) == 2:
                        s_val = TimeParser.parse_time(parts[0])
                        e_val = TimeParser.parse_time(parts[1])
                        if s_val is not None and e_val is not None and e_val > s_val:
                            sess["trim_enabled"] = True
                            sess["start_time"] = s_val
                            sess["end_time"] = e_val
                            bot.reply_to(
                                reply_msg,
                                f"✅ Kırpma ayarlandı: {TimeParser.format_duration(s_val)} - {TimeParser.format_duration(e_val)}",
                            )
                        else:
                            bot.reply_to(reply_msg, "⚠️ Geçersiz zaman aralığı. Kırpma değiştirilmedi.")
                    else:
                        bot.reply_to(reply_msg, "⚠️ Biçim anlaşılamadı (Örn: 01:20 - 02:45).")

                card_text, card_markup = build_studio_card(sess)

            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=card_text,
                    reply_markup=card_markup,
                )
            except Exception:
                pass

        bot.register_next_step_handler(msg, process_trim_input)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("menu_rename:"))
    def cb_menu_rename(call):
        session_id = call.data.split(":")[1]
        with sessions_lock:
            session = user_sessions.get(session_id)
            if not session:
                bot.answer_callback_query(call.id, "Oturum süresi dolmuş.", show_alert=True)
                return

        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "✏️ <b>Yeni Dosya Başlığını Yazın:</b>",
            reply_markup=types.ForceReply(selective=True),
        )

        def process_rename_input(reply_msg):
            new_title = (reply_msg.text or "").strip()
            with sessions_lock:
                sess = user_sessions.get(session_id)
                if not sess:
                    return
                if new_title:
                    sess["custom_title"] = new_title
                    bot.reply_to(reply_msg, f"✅ Başlık güncellendi: <b>{new_title}</b>")
                card_text, card_markup = build_studio_card(sess)

            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=card_text,
                    reply_markup=card_markup,
                )
            except Exception:
                pass

        bot.register_next_step_handler(msg, process_rename_input)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("start_dl:"))
    def cb_start_download(call):
        session_id = call.data.split(":")[1]
        with sessions_lock:
            session = user_sessions.get(session_id)
            if not session:
                bot.answer_callback_query(call.id, "Oturum süresi dolmuş. Lütfen tekrar link girin.", show_alert=True)
                return

        bot.answer_callback_query(call.id, "İndirme başlatılıyor...")

        fmt = session.get("format", "MP4")
        q = session.get("quality", "")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"⏳ <b>İndiriliyor ve işleniyor...</b>\nFormat: <code>{fmt}</code> | Kalite: <code>{q}</code>\nLütfen bekleyin...",
            reply_markup=None,
        )

        def download_worker():
            temp_task_dir = tempfile.mkdtemp(dir=TEMP_DOWNLOAD_DIR)
            try:
                is_audio = fmt in ["MP3", "WAV"]
                bot.send_chat_action(
                    call.message.chat.id,
                    "upload_document" if is_audio else "upload_video",
                )

                file_path = download_media_file(session, temp_task_dir)
                if not os.path.exists(file_path):
                    raise RuntimeError("İndirilen dosya bulunamadı.")

                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

                if file_size_mb > 49.5:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=(
                            f"⚠️ <b>Dosya Telegram sınırının üzerinde ({file_size_mb:.1f} MB)</b>\n\n"
                            f"Telegram Botları maksimum 50 MB gönderebilmektedir.\n"
                            f"Daha düşük bir çözünürlük veya <b>MP3</b> seçebilir ya da kırpma aralığını kısaltabilirsiniz."
                        ),
                    )
                    return

                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=f"📤 <b>Dosya hazırlandı ({file_size_mb:.1f} MB), Telegram'a yükleniyor...</b>",
                    )
                except Exception:
                    pass

                base_name = os.path.splitext(os.path.basename(file_path))[0]

                with open(file_path, "rb") as f:
                    if fmt == "MP4":
                        bot.send_video(
                            chat_id=call.message.chat.id,
                            video=f,
                            caption="✅ <b>İndirme Tamamlandı!</b>\n📱 <i>iPhone'da videoya basılı tutup 'Videoyu Kaydet' diyerek galerine alabilirsin.</i>",
                            supports_streaming=True,
                            timeout=300,
                        )
                    elif fmt in ["MP3", "WAV"]:
                        bot.send_audio(
                            chat_id=call.message.chat.id,
                            audio=f,
                            title=base_name,
                            performer=session.get("uploader", "Universal Downloader"),
                            caption="✅ <b>Ses İndirme Tamamlandı!</b>",
                            timeout=300,
                        )
                    else:
                        bot.send_document(
                            chat_id=call.message.chat.id,
                            document=f,
                            caption="✅ <b>Dosya İndirildi!</b>",
                            timeout=300,
                        )

                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except Exception:
                    pass

            except Exception as e:
                err_text = str(e)
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=f"❌ İndirme sırasında hata oluştu:\n<code>{err_text[:250]}</code>",
                    )
                except Exception:
                    pass
            finally:
                if os.path.exists(temp_task_dir):
                    shutil.rmtree(temp_task_dir, ignore_errors=True)
                with sessions_lock:
                    user_sessions.pop(session_id, None)

        threading.Thread(target=download_worker, daemon=True).start()

    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"Bağlantı uyarısı: {e}. 5 saniye içinde tekrar deneniyor...")
            import time
            time.sleep(5)


if __name__ == "__main__":
    main()
