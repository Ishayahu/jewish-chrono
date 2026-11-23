@echo off
setlocal
chcp 65001 >nul
title Семейный бюджет - публикация из LibreOffice Calc

set "BOOK=%USERPROFILE%\OneDrive\Documents\Бюджет_2.ods"
set "SCRIPT_DIR=%~dp0"
set "TEMP_SOURCE=%TEMP%\calc-publisher-%RANDOM%-%RANDOM%"
set "SOURCE_BASE=https://raw.githubusercontent.com/Ishayahu/jewish-chrono/main/finance"

echo.
echo =============================================================
echo  Экспорт финансового дашборда из сохранённого LibreOffice Calc
echo =============================================================
echo.
if not exist "%BOOK%" (
  echo ОШИБКА: файл книги не найден: "%BOOK%"
  echo Сохраните таблицу и поправьте BOOK в начале этого .cmd при другом пути.
  goto :failed
)
where py >nul 2>nul
if errorlevel 1 (
  echo ОШИБКА: не установлен Python launcher py
  goto :failed
)

echo Обновляю два Python-модуля из вашего репозитория GitHub...
mkdir "%TEMP_SOURCE%" 2>nul
powershell -NoProfile -NonInteractive -Command "$ErrorActionPreference='Stop'; $base='%SOURCE_BASE%'; $dir='%TEMP_SOURCE%'; Invoke-WebRequest -Uri ($base+'/publish_from_calc.py') -OutFile (Join-Path $dir 'publish_from_calc.py'); Invoke-WebRequest -Uri ($base+'/local_calc_model.py') -OutFile (Join-Path $dir 'local_calc_model.py')"
if errorlevel 1 (
  echo ОШИБКА: не получилось загрузить актуальные Python-файлы.
  echo Публикация не начата. Проверьте доступ к raw.githubusercontent.com.
  goto :failed
)
py -m py_compile "%TEMP_SOURCE%\publish_from_calc.py" "%TEMP_SOURCE%\local_calc_model.py"
if errorlevel 1 (
  echo ОШИБКА: загруженный Python не прошёл проверку синтаксиса.
  goto :failed
)
copy /Y "%TEMP_SOURCE%\publish_from_calc.py" "%SCRIPT_DIR%publish_from_calc.py" >nul
if errorlevel 1 goto :failed
copy /Y "%TEMP_SOURCE%\local_calc_model.py" "%SCRIPT_DIR%local_calc_model.py" >nul
if errorlevel 1 goto :failed
rmdir /S /Q "%TEMP_SOURCE%" 2>nul

py -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; from zoneinfo import ZoneInfo; ZoneInfo('Europe/Moscow')" >nul 2>nul
if errorlevel 1 (
  echo Устанавливаю недостающие зависимости Python...
  py -m pip install cryptography tzdata
  if errorlevel 1 goto :failed
)

echo.
echo Проверка бюджета, фиксация дневной цели и публикация двух шифротекстов.
echo Если ключи уже настроены, программа их использует.
echo При отсутствии токена GitHub может быть предложен скрытый ввод.
echo.
py "%SCRIPT_DIR%publish_from_calc.py" --book "%BOOK%" --publish
if errorlevel 1 goto :failed

echo.
echo Отправка в GitHub прошла успешно.
echo После успешного GitHub Actions сайт покажет новый снимок:
echo https://ishayahu.github.io/jewish-chrono/finance/
echo.
pause
exit /b 0

:failed
echo.
echo ПУБЛИКАЦИЯ ОСТАНОВЛЕНА. Не передавайте токены и пароли.
if exist "%TEMP_SOURCE%" rmdir /S /Q "%TEMP_SOURCE%" 2>nul
echo Пришлите текст ошибки без секретов.
pause
exit /b 1
