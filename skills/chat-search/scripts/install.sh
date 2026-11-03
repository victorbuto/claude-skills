#!/bin/bash
# Ставит chat-search: рабочую копию, команду в терминале и фоновое обновление.
#
# Зачем копия: macOS не пускает фоновые задачи (launchd) в ~/Documents,
# поэтому исполняемый скрипт живёт в ~/.local/bin, а исходник — в скилле.
set -e

SRC="$(cd "$(dirname "$0")" && pwd)/chatsearch.py"
BIN="$HOME/.local/bin/chat-search"
PLIST="$HOME/Library/LaunchAgents/com.chatsearch.index.plist"

mkdir -p "$HOME/.local/bin" "$HOME/Library/Application Support/chat-search"

cp "$SRC" "$BIN"
chmod +x "$BIN"
echo "команда установлена: $BIN"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.chatsearch.index</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$BIN</string>
        <string>index</string>
    </array>
    <key>StartInterval</key><integer>300</integer>
    <key>RunAtLoad</key><true/>
    <key>ProcessType</key><string>Background</string>
    <key>LowPriorityIO</key><true/>
    <key>Nice</key><integer>5</integer>
    <key>StandardOutPath</key><string>$HOME/Library/Application Support/chat-search/index.log</string>
    <key>StandardErrorPath</key><string>$HOME/Library/Application Support/chat-search/index.err</string>
</dict>
</plist>
PLIST_EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "фоновое обновление включено: раз в 5 минут"

sleep 2
if [ -s "$HOME/Library/Application Support/chat-search/index.err" ]; then
  echo "ВНИМАНИЕ, есть ошибки:"
  tail -3 "$HOME/Library/Application Support/chat-search/index.err"
else
  echo "ошибок нет"
fi
