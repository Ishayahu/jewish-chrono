@echo off
setlocal
chcp 65001 >nul
title LibreOffice Calc - Publish encrypted financial dashboard

set "BOOK=%USERPROFILE%\OneDrive\Documents\Бюджет_2.ods"
set "PYFILE=%~dp0publish_from_calc.py"

echo.
echo ===========================================================
echo  ПУБЛИКАЦИЯ: только зашифрованные данные из сохранённого Calc
echo ===========================================================
echo.
if not exist "%BOOK%" (
  echo ОШИБКА: не найдена таблица "%BOOK%".
  echo Сохраните рабочую книгу под этим именем или поправьте BOOK в начале файла.
  goto :failed
)
if not exist "%PYFILE%" (
  echo ОШИБКА: не найден publish_from_calc.py рядом с этим файлом.
  echo Скачайте актуальные скрипты из репозитория.
  goto :failed
)
where py >nul 2>nul
if errorlevel 1 (
  echo ОШИБКА: не найден Python launcher "py". Установите Python 3.11 или новее.
  goto :failed
)
py -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; from zoneinfo import ZoneInfo; ZoneInfo('Europe/Moscow')" >nul 2>nul
if errorlevel 1 (
  echo Устанавливаю отсутствующие библиотеки cryptography и tzdata...
  py -m pip install cryptography tzdata
  if errorlevel 1 goto :failed
)
echo.
echo Сценарий: сохранить сегодняшнюю фиксированную цель.
echo Скрипт читает данные Calc, расшифровывает прежнее состояние и
echo отправляет в GitHub только зашифрованные owner.enc и family.enc.
echo.
echo Если GitHub CLI уже авторизован, вход происходит автоматически.
echo Иначе скрипт спросит GitHub token скрытым вводом.
echo Пароли дашбордов будут запрошены только если их нет в среде.
echo.
py "%PYFILE%" --book "%BOOK%" --publish
if errorlevel 1 goto :failed

echo.
echo GitHub принял шифрованные данные. Сайт будет обновлён GitHub Actions.
echo В браузере проверьте после успешного запуска workflow:
echo https://ishayahu.github.io/jewish-chrono/finance/
echo.
pause
exit /b 0

:failed
echo.
echo GitHub не получил новую публикацию от этого запуска.
echo Скопируйте сообщение об ошибке без паролей и токенов.
echo.
pause
exit /b 1
