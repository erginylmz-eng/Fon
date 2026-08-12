@echo off
REM ============================================================
REM TEFAS Veri Guncelleme - Yerel Calistirma Betigi
REM Bu dosyayi repo klasorunuzun KOKUNE koyun (scripts, data, docs
REM klasorleriyle ayni seviyede). Windows Gorev Zamanlayici bu
REM dosyayi calistirarak eksik gunleri ceker ve GitHub'a gonderir.
REM ============================================================

setlocal
cd /d "%~dp0"

echo. >> update_log.txt
echo [%date% %time%] TEFAS veri guncelleme basladi >> update_log.txt

python scripts\fetch_and_build.py >> update_log.txt 2>&1
if errorlevel 1 (
    echo [%date% %time%] HATA: fetch_and_build.py basarisiz oldu, commit atlaniyor. >> update_log.txt
    goto :son
)

git add data\tefas_veri.json data\fon_valor.csv docs\index.html docs\karar.html docs\karsilastir.html
git diff --staged --quiet
if errorlevel 1 (
    git commit -m "TEFAS verisi guncellendi - yerel bilgisayardan (%date%)" >> update_log.txt 2>&1
    git push >> update_log.txt 2>&1
    echo [%date% %time%] Degisiklikler GitHub'a gonderildi. >> update_log.txt
) else (
    echo [%date% %time%] Yeni veri yok, commit atlandi (zaten guncel). >> update_log.txt
)

:son
echo [%date% %time%] Islem tamamlandi. >> update_log.txt
endlocal
