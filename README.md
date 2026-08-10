TEFAS Para Piyasası Fonları — Günlük Getiri Raporu
Ziraat Portföy, İş Portföy, Ak Portföy, Garanti BBVA Portföy, Yapı Kredi Portföy,
Deniz Portföy, QNB Finans Portföy ve TEB Portföy'ün sunduğu, risk değeri 1/7 veya
2/7 olan Para Piyasası fonlarının günlük fiyat/getiri takibini yapar.
Veri: `data/tefas_veri.json` — her fon için tarih/fiyat geçmişi (bu dosya
"veritabanı" görevi görür, her gün otomatik güncellenir).
Site: `docs/index.html` — GitHub Pages ile yayınlanan, firma bazlı
bölümlenmiş günlük getiri raporu.
Otomasyon: `.github/workflows/daily-update.yml` — hafta içi her sabah
09:00 (TR saati) otomatik çalışıp veriyi günceller ve raporu yeniden üretir.
Kurulum (bir kerelik)
Bu klasördeki dosyaları GitHub'da yeni, boş bir repoya push edin:
```bash
   cd tefas-github
   git remote add origin https://github.com/<kullanici-adiniz>/<repo-adi>.git
   git branch -M main
   git push -u origin main
   ```
(Bu klasör zaten bir git deposu olarak hazırlandı ve ilk commit yapıldı;
sadece `remote add` ve `push` yapmanız yeterli.)
GitHub Pages'i açın: Repo → Settings → Pages → "Build and deployment"
altında Source: Deploy from a branch, Branch: main, klasör: /docs
seçip kaydedin. Birkaç dakika içinde siteniz şu adreste yayında olur:
`https://<kullanici-adiniz>.github.io/<repo-adi>/`
Actions'ın açık olduğundan emin olun: Repo → Settings → Actions →
General → "Allow all actions" seçili olmalı (genelde varsayılan böyledir).
İlk çalıştırmayı elle tetikleyip test edin: Repo → Actions →
"TEFAS Günlük Güncelleme" → "Run workflow".
ÖNEMLİ — Bilinen risk: TEFAS bot koruması
TEFAS'ın `fon-verileri` sayfası JavaScript ile render ediliyor ve bir bot
koruması (WAF, Akamai/Imperva benzeri) barındırıyor. Bu yüzden script gerçek
bir tarayıcı (Playwright/headless Chromium) kullanıyor. Yine de:
Bulut IP'leri (GitHub Actions runner'ları dahil) bazı WAF'lar tarafından
tarayıcı gerçekçiliğinden bağımsız olarak engellenebilir. Bu gerçekleşirse
workflow "Request Rejected" hatasıyla başarısız olur ve veri/rapor
değiştirilmez (script kasıtlı olarak hata ile çıkar, bozuk veri yazmaz).
İlk çalıştırmada bunu görürseniz (Actions sekmesinde kırmızı ✗), TEFAS bu
IP aralığını engelliyor demektir. Bu durumda alternatifler:
Self-hosted bir GitHub Actions runner (kendi bilgisayarınızda/VPS'inizde,
farklı bir IP'den) kullanmak,
Ya da mevcut Cowork zamanlanmış görevini (Claude in Chrome ile, sizin
gerçek tarayıcınız üzerinden) yedek/birincil yöntem olarak kullanmaya
devam etmek.
Yerelde test etme
```bash
pip install -r requirements.txt
playwright install chromium
python scripts/fetch_and_build.py
```
Yeni fon eklemek / çıkarmak (kod yazmadan!)
Takip edilen fonların listesi `data/fon_listesi.csv` dosyasında tutulur.
Yeni bir fon eklemek için:
GitHub'da bu dosyayı açın (`data/fon_listesi.csv`) ve sağ üstteki kalem
(✏️) ikonuna tıklayıp düzenleme moduna geçin.
Yeni bir satır ekleyin: `FONKODU,Firma Adı,Risk`
`FONKODU`: TEFAS'taki fon kodu (büyük harf, örn. `YPT`)
`Firma Adı`: raporda hangi başlık altında görüneceği (istediğiniz metni
yazabilirsiniz, örn. `Yapı Kredi Portföy`)
`Risk`: TEFAS'taki risk değeri (1-7), bilmiyorsanız boş bırakabilirsiniz
Commit changes deyin.
Fonu çıkarmak isterseniz aynı şekilde ilgili satırı silip commit'leyin.
Bir sonraki otomatik çalıştırmada (veya Actions sekmesinden elle
"Run workflow" derseniz hemen) yeni fon TEFAS'tan çekilip fon adıyla birlikte
otomatik olarak rapora eklenir — kod değişikliği veya bana tekrar sormanıza
gerek kalmaz.
> Not: Eklediğiniz kodun gerçek bir TEFAS fon kodu olması gerekir (fon
> detay sayfasının adresindeki kod, örn. `tefas.gov.tr/tr/fon-detayli-analiz/AAL`
> adresindeki `AAL`). Yanlış/olmayan bir kod eklerseniz o fon için veri
> bulunamaz ve script uyarı verip diğer fonlarla devam eder.
Fon listesi (güncel liste `data/fon_listesi.csv` içindedir)
Firma	Fon Kodları
Ziraat Portföy	HLL, TZL, ZBJ
İş Portföy	IOO, IOP, IUZ, TI1
Ak Portföy	ALE, ANL, BGP, SAP
Garanti BBVA Portföy	GAL, GNP, GPZ, GTL
Yapı Kredi Portföy	PPI, YLB, YVD
Deniz Portföy	DCN, DL2, DLY
QNB Finans Portföy	ENR, FI5, FSK, OPJ, YMP
TEB Portföy	BRG, IGL, PTL, PYB, SKL, TKM
Bu rapor bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.
