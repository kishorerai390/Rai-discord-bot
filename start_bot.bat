@echo off
title MusicMaid Vocard Launcher
echo ========================================================
echo        Starting Lavalink v4.2.2 Audio Server...
echo ========================================================
start "Lavalink Server" /d "F:\Bot-Staging\lavalink" java -jar Lavalink.jar

echo Waiting for Lavalink to initialize...
timeout /t 5 /nobreak >nul

echo ========================================================
echo        Starting MusicMaid Vocard Bot...
echo ========================================================
python main.py
pause
