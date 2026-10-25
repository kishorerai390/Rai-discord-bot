#!/bin/bash
set -e
echo "=== Running Render Build for MusicMaid ==="
pip install -r requirements.txt

# Download portable JRE 21 if not present
if [ ! -d "jre/bin" ]; then
    echo "Downloading Temurin JRE 21..."
    curl -L -o jre.tar.gz https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.6%2B7/OpenJDK21U-jre_x64_linux_hotspot_21.0.6_7.tar.gz
    mkdir -p jre
    tar -xzf jre.tar.gz -C jre --strip-components=1
    rm -f jre.tar.gz
    echo "JRE 21 installed successfully."
fi

# Download Lavalink v4.2.2 if not present
mkdir -p lavalink
if [ ! -f "lavalink/Lavalink.jar" ]; then
    echo "Downloading Lavalink v4.2.2..."
    curl -L -o lavalink/Lavalink.jar https://github.com/lavalink-devs/Lavalink/releases/download/4.2.2/Lavalink.jar
    echo "Lavalink downloaded successfully."
fi

echo "=== Build Completed ==="
