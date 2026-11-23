@echo off
setlocal
chcp 65001 >nul
title LibreOffice Calc - Finance Export

set "BOOK=%USERPROFILE%\OneDrive\Documents\Бюджет_2.ods"
set "PREVIOUS=%USERPROFILE%\OneDrive\Documents\owner.enc"
set "OUTPUT=%USERPROFILE%\finance-export"
set "PYFILE=%~dp0publish_from_calc.py"

echo.
echo ==== ПРОВЕРОЧНАЯ ЗАШИФРОВАННАЯ ВЫГРУЗКА ====
echo.
if not exist "%BOOK%" (
  echo ОШИБКА: не найден файл %BOOK%
  echo Сохраните исправленную книгу под указанным именем.
  goto :failed
)
if not exist "%PREVIOUS%" if not exist "%OUTPUT%\owner.enc" (
  echo ОШИБКА: не найден исходный owner.enc в Documents.
  echo Сохраните ранее скачанный owner.enc рядом с книгой.
  goto :failed
)
where py >nul 2>nul
if errorlevel 1 (
  echo ОШИБКА: команда py не найдена. Требуется установленный Python 3.11 или новее.
  goto :failed
)

py -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; from zoneinfo import ZoneInfo; ZoneInfo('Europe/Moscow')" >nul 2>nul
if errorlevel 1 (
  echo Проверяем или устанавливаем библиотеки cryptography и tzdata...
  py -m pip install cryptography tzdata
  if errorlevel 1 goto :failed
)

echo.
echo Если пароли не заданы в среде Windows, программа спросит ДЕЙСТВУЮЩИЕ пароли.
echo Ввод паролей будет скрыт. Новые пароли придумывать НЕ надо.
echo.
py "%PYFILE%" --book "%BOOK%" --export-only --previous-owner "%PREVIOUS%" --output-dir "%OUTPUT%"
if errorlevel 1 goto :failed

echo.
echo УСПЕШНО: создана локальная зашифрованная выгрузка.
echo Файлы: %OUTPUT%\owner.enc и family.enc
echo Данные в GitHub НЕ ОТПРАВЛЕНЫ.
echo.
pause
exit /b 0

:failed
echo.
echo Публикация НЕ ПРОИЗВЕДЕНА. Отправьте мне текст ошибки, но НЕ пароли.
echo.
pause
exit /b 1
