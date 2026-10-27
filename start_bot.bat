@echo off
title Rem Launcher 🎧💜
echo ========================================================
echo        Starting Lavalink v4.2.2 Audio Server...
echo ========================================================
start "Lavalink Server" /d "F:\Bot-Staging\lavalink" java -jar Lavalink.jar

echo Waiting for Lavalink to initialize...
timeout /t 5 /nobreak >nul

:bot_loop
echo ========================================================
echo        Starting Rem Bot (Anime Music Companion)...
echo ========================================================
python main.py
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% EQU 42 (
    echo.
    echo ========================================================
    echo  [Rem AutoUpdater] Code update / restart requested (Code 42)
    echo  Pulling latest updates from GitHub...
    echo ========================================================
    git pull origin feature/vocard-bot
    echo Checking Python dependencies...
    pip install -r requirements.txt --quiet
    echo Restarting Rem Bot...
    timeout /t 2 /nobreak >nul
    goto bot_loop
)

if %EXIT_CODE% NEQ 0 (
    echo.
    echo [Rem Launcher] Process exited with error code %EXIT_CODE%.
    pause
)
