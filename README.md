# ⚡ Gelişmiş Medya İndirici & Kırpıcı (Universal Downloader)

Python, CustomTkinter, yt-dlp ve FFmpeg kullanılarak geliştirilmiş modern ve güçlü bir masaüstü video/ses indirme uygulaması.

---

## 🌟 Özellikler

- **Geniş Platform Desteği**: YouTube, TikTok, Instagram, Twitter/X, Facebook, Twitch, Vimeo ve yt-dlp tarafından desteklenen 1000'den fazla platform.
- **Format Seçenekleri**: 
  - `MP4 (Video)`
  - `MP3 (Ses)` (FFmpeg ile yüksek kaliteli ses dönüştürme)
- **Kalite Seçimi**:
  - Video için: `En Yüksek (Best)`, `4K (2160p)`, `2K (1440p)`, `1080p (Full HD)`, `720p (HD)`, `480p (SD)`, `360p (Düşük)`
  - Ses için: `320 kbps`, `256 kbps`, `192 kbps`, `128 kbps`, `64 kbps`
- **Zaman Aralığı Kırpma (Trim / Clip)**:
  - Başlangıç ve bitiş süresi belirterek videonun veya sesin sadece istenen kısmını indirme (Örn: `00:01:20` - `00:02:45`, `01:20` - `02:45` veya saniye cinsinden `80` - `165`).
- **Canlı İlerleme ve İstatistikler**:
  - Animasyonlu CustomTkinter ilerleme çubuğu (Progress Bar)
  - Gerçek zamanlı indirme yüzdesi (`%`), anlık hız (`MB/s`), indirilen/toplam boyut (`MB`) ve tahmini kalan süre (`ETA`)
  - Detaylı durum bildirimleri
- **Kullanıcı Dostu Önizleme**:
  - Video başlığı, kanal/yükleyici adı, süre ve kapak resmi (thumbnail) önizlemesi
- **İndirme Sonrası Hızlı İşlemler**:
  - Dosyayı doğrudan varsayılan oynatıcıda açma
  - Dosyayı Windows Gezgini'nde seçili olarak gösterme
- **FFmpeg Entegrasyonu**:
  - Sistemdeki FFmpeg'i, yerel klasördeki FFmpeg'i veya `imageio-ffmpeg` ikili dosyasını otomatik olarak algılar ve yapılandırır.

---

## 🚀 Kurulum ve Çalıştırma

### 1. Gereksinimleri Yükleme
```bash
pip install -r requirements.txt
```

### 2. Masaüstü Uygulamasını Başlatma
```bash
python app.py
```
veya Windows üzerinde `run.bat` dosyasına çift tıklayabilirsiniz.

### 3. Telegram Botunu Başlatma (Mobil / iPhone için)
```bash
python bot.py
```
veya Windows üzerinde `run_bot.bat` dosyasına çift tıklayabilirsiniz.
İlk çalıştırmada Telegram BotFather'dan aldığınız API Token'ı girmeniz yeterlidir.

