@echo off
REM ============================================================
REM TEFAS Takip - Tum Degisiklikleri GitHub'a Gonder
REM Bu dosyaya cift tiklayarak, klasordeki hangi dosya degismis
REM olursa olsun tumunu GitHub'a gonderebilirsiniz.
REM ============================================================

setlocal
cd /d "%~dp0"

echo ============================================
echo TEFAS Takip - GitHub'a Gonderiliyor...
echo ============================================
echo.

REM Onceki bir islemden kalmis olabilecek kilit dosyasini temizle
if exist ".git\index.lock" del /f /q ".git\index.lock"

git add -A

git commit -m "Guncelleme %date% %time%"
if errorlevel 1 (
    echo.
    echo Gonderilecek yeni bir degisiklik yok ^(zaten guncel^), yine de push deneniyor...
)

echo.
echo GitHub'a gonderiliyor...
git push

echo.
if errorlevel 1 (
    echo ============================================
    echo HATA: Gonderim basarisiz oldu. Yukaridaki mesaji kontrol edin.
    echo ============================================
) else (
    echo ============================================
    echo TAMAMLANDI: Tum degisiklikler GitHub'a gonderildi.
    echo ============================================
)

echo.
pause
endlocal
