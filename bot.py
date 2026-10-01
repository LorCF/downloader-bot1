import os
import sys
import re
import json
import shutil
import tempfile
import threading
from typing import Optional, Dict, Any

import telebot
from telebot import types
import yt_dlp

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_config.json")
TEMP_DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_downloads")


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
    print("Bot Token bulunamadı!")
    print("1. Telegram'da @BotFather hesabına git.")
    print("2. /newbot komutunu yaz ve adımları takip et.")
    print("3. Sana verilen API Token'ı kopyala.")
    print("=" * 60)
    
    token = input("Bot Token'ı buraya yapıştır ve Enter'a bas: ").strip()
    if token:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"bot_token": token}, f, indent=4)
        print("✅ Token 'bot_config.json' dosyasına kaydedildi!")
        return token

    print("❌ Geçerli bir token girilmedi. Program sonlandırılıyor.")
    sys.exit(1)


user_url_sessions = {}
session_lock = threading.Lock()


def extract_first_url(text: str) -> Optional[str]:
    url_pattern = r"(https?://[^\s]+)"
    match = re.search(url_pattern, text)
    if match:
        return match.group(1).strip()
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


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None or seconds <= 0:
        return "--:--"
    total_secs = int(round(seconds))
    hours, remainder = divmod(total_secs, 3600)
    mins, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def download_media(url: str, mode: str, output_folder: str) -> str:
    ffmpeg_exe = FFmpegHelper.get_ffmpeg_path()
    cookie_path = get_cookie_file_path()
    os.makedirs(output_folder, exist_ok=True)
    outtmpl = os.path.join(output_folder, "%(title).80B [%(id)s].%(ext)s")

    ydl_opts = {
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

    if mode == "audio":
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ]
    else:
        ydl_opts["format"] = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
        ydl_opts["merge_output_format"] = "mp4"
        ydl_opts["postprocessor_args"] = {
            "merger": ["-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart"],
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if mode == "audio":
            base, _ = os.path.splitext(filename)
            filename = f"{base}.mp3"
        elif mode == "video":
            base, _ = os.path.splitext(filename)
            mp4_file = f"{base}.mp4"
            if os.path.exists(mp4_file):
                filename = mp4_file

        if not os.path.exists(filename):
            for candidate in os.listdir(output_folder):
                full_cand = os.path.join(output_folder, candidate)
                if os.path.isfile(full_cand):
                    return full_cand

        return filename


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
        print(f"🌐 Cloud Health Check sunucusu port {port} uzerinde baslatildi.")
    except Exception as e:
        print(f"Health server baslatilamadi: {e}")


def main():
    start_health_server()
    token = load_token()
    bot = telebot.TeleBot(token, parse_mode="HTML")
    os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)

    print("\n🚀 Telegram Downloader Bot başarıyla başlatıldı!")
    print("📱 iPhone veya telefonundan bota herhangi bir link gönderebilirsin.")
    print("Durdurmak için konsolda Ctrl + C tuşlarına basabilirsin.\n")

    @bot.message_handler(commands=["start"])
    def handle_start(message):
        welcome_text = (
            "👋 <b>Merhaba! Medya İndirici Botuna Hoş Geldin.</b>\n\n"
            "Bu bot ile YouTube, TikTok, Instagram, Twitter/X, Facebook ve 1000'den fazla "
            "platformdaki video ve sesleri kolayca indirebilirsin.\n\n"
            "⚡ <b>Nasıl Kullanılır?</b>\n"
            "1. İndirmek istediğin videonun linkini buraya yapıştır ve gönder.\n"
            "2. Çıkan butonlardan <b>Video (MP4)</b> veya <b>Ses (MP3)</b> seç.\n"
            "3. Bot dosyayı indirip sana gönderecektir!\n\n"
            "📱 <i>iPhone Kullanıcıları İçin İpucu:</i>\n"
            "Gelen videoya basılı tutup <b>'Videoyu Kaydet'</b> diyerek doğrudan Fotoğraflar galerine kaydedebilirsin."
        )
        bot.reply_to(message, welcome_text)

    @bot.message_handler(commands=["help"])
    def handle_help(message):
        help_text = (
            "ℹ️ <b>Yardım & Bilgi</b>\n\n"
            "• <b>Desteklenen Siteler:</b> YouTube, Instagram (Reels/Post), TikTok, X/Twitter, Pinterest, Facebook, Vimeo vb.\n"
            "• <b>Formatlar:</b> MP4 (Video) ve MP3 (Yüksek Kalite Ses)\n"
            "• <b>Dosya Boyutu Sınırı:</b> Telegram Bot API kuralı gereği gönderilen dosyalar maksimum 50 MB olabilir.\n\n"
            "Herhangi bir link göndererek hemen başlayabilirsin!"
        )
        bot.reply_to(message, help_text)

    @bot.message_handler(func=lambda msg: True)
    def handle_incoming_message(message):
        text = message.text or ""
        url = extract_first_url(text)

        if not url:
            bot.reply_to(
                message,
                "⚠️ Lütfen geçerli bir video veya ses linki gönderin.\n"
                "Örnek: YouTube, Instagram Reels, TikTok, Twitter vb."
            )
            return

        status_msg = bot.reply_to(message, "🔍 <i>Link taranıyor, bilgiler alınıyor...</i>")

        def fetch_worker():
            try:
                info = get_media_info(url)
                title = info.get("title", "Bilinmeyen Başlık")
                duration = format_duration(info.get("duration"))
                uploader = info.get("uploader") or info.get("channel") or "Bilinmiyor"

                clean_title = (title[:120] + "...") if len(title) > 120 else title

                response_text = (
                    f"🎬 <b>{clean_title}</b>\n\n"
                    f"👤 <b>Yükleyici:</b> {uploader}\n"
                    f"⏱️ <b>Süre:</b> {duration}\n\n"
                    f"Lütfen indirmek istediğin formatı seç:"
                )

                session_id = f"{message.chat.id}_{message.message_id}"
                with session_lock:
                    user_url_sessions[session_id] = url

                markup = types.InlineKeyboardMarkup(row_width=2)
                btn_video = types.InlineKeyboardButton(
                    "🎬 Video (MP4)",
                    callback_data=f"dl:video:{session_id}"
                )
                btn_audio = types.InlineKeyboardButton(
                    "🎵 Ses (MP3)",
                    callback_data=f"dl:audio:{session_id}"
                )
                markup.add(btn_video, btn_audio)

                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    text=response_text,
                    reply_markup=markup
                )

            except Exception as e:
                err_text = str(e)
                if "Unsupported URL" in err_text:
                    err_msg = "❌ Bu platform veya link desteklenmiyor."
                else:
                    err_msg = f"❌ Bilgiler alınırken bir sorun oluştu:\n<code>{err_text[:200]}</code>"

                try:
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        text=err_msg
                    )
                except Exception:
                    pass

        threading.Thread(target=fetch_worker, daemon=True).start()

    @bot.callback_query_handler(func=lambda call: call.data.startswith("dl:"))
    def handle_download_callback(call):
        parts = call.data.split(":")
        if len(parts) < 3:
            bot.answer_callback_query(call.id, "Geçersiz istek.")
            return

        mode = parts[1]
        session_id = parts[2]

        with session_lock:
            url = user_url_sessions.get(session_id)

        if not url:
            bot.answer_callback_query(call.id, "Oturum süresi dolmuş. Lütfen linki tekrar gönderin.", show_alert=True)
            return

        bot.answer_callback_query(call.id, "İndirme başlatıldı...")
        mode_text = "Video (MP4)" if mode == "video" else "Ses (MP3)"

        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"⏳ <b>{mode_text} indiriliyor ve dönüştürülüyor...</b>\nBu işlem dosya boyutuna göre biraz zaman alabilir.",
                reply_markup=None
            )
        except Exception:
            pass

        def download_worker():
            temp_task_dir = tempfile.mkdtemp(dir=TEMP_DOWNLOAD_DIR)
            try:
                bot.send_chat_action(
                    call.message.chat.id,
                    "upload_video" if mode == "video" else "upload_document"
                )
                file_path = download_media(url, mode, temp_task_dir)

                if not os.path.exists(file_path):
                    raise RuntimeError("İndirilen dosya bulunamadı.")

                file_size_bytes = os.path.getsize(file_path)
                file_size_mb = file_size_bytes / (1024 * 1024)

                if file_size_mb > 49.5:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=(
                            f"⚠️ <b>Dosya çok büyük ({file_size_mb:.1f} MB)</b>\n\n"
                            f"Telegram Botları maksimum 50 MB dosya gönderebilmektedir.\n"
                            f"Dilerseniz aynı linki gönderip <b>Ses (MP3)</b> olarak indirebilirsiniz."
                        )
                    )
                    return

                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=f"📤 <b>{mode_text} hazırlandı ({file_size_mb:.1f} MB), Telegram'a yükleniyor...</b>"
                    )
                except Exception:
                    pass

                base_filename = os.path.basename(file_path)

                with open(file_path, "rb") as f:
                    if mode == "video":
                        bot.send_video(
                            chat_id=call.message.chat.id,
                            video=f,
                            caption="✅ <b>İndirme Tamamlandı!</b>\n📱 <i>iPhone'da videoya basılı tutup 'Videoyu Kaydet' diyerek galerine ekleyebilirsin.</i>",
                            supports_streaming=True,
                            timeout=300
                        )
                    else:
                        bot.send_audio(
                            chat_id=call.message.chat.id,
                            audio=f,
                            caption="✅ <b>Ses İndirme Tamamlandı!</b>",
                            title=os.path.splitext(base_filename)[0],
                            timeout=300
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
                        text=f"❌ İndirme sırasında bir hata oluştu:\n<code>{err_text[:200]}</code>"
                    )
                except Exception:
                    pass
            finally:
                if os.path.exists(temp_task_dir):
                    shutil.rmtree(temp_task_dir, ignore_errors=True)
                with session_lock:
                    user_url_sessions.pop(session_id, None)

        threading.Thread(target=download_worker, daemon=True).start()

    while True:
        try:
            bot.infinity_polling(timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"Bağlantı hatası: {e}. 5 saniye içinde tekrar deneniyor...")
            import time
            time.sleep(5)


if __name__ == "__main__":
    main()
