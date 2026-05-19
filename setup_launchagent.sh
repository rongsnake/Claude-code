#!/bin/bash

# Create LaunchAgent plist for Claude Code
PLIST_PATH="$HOME/Library/LaunchAgents/com.anthropic.claude-code.plist"
LOG_DIR="$HOME/Library/Logs/claude-code"
CLAUDE_BIN=$(which claude)

# Verify Claude Code is installed
if [ -z "$CLAUDE_BIN" ]; then
    echo "Error: Claude Code not found. Install it first with: curl -fsSL https://claude.ai/install.sh | sh"
    exit 1
fi

# Create log directory and LaunchAgents directory if needed
mkdir -p "$LOG_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

# Create the plist file (using variable expansion, not single-quoted heredoc)
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.anthropic.claude-code</string>
    <key>ProgramArguments</key>
    <array>
        <string>${CLAUDE_BIN}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/claude-code.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/claude-code.error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
EOF

# (Re)load the LaunchAgent — unload first to handle the already-loaded case
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

# Disable sleep mode so the service stays alive
pmset -a sleep 0
pmset -a disablesleep 1

echo "Setup complete. Claude Code is now running as a background service."
echo "Logs:          $LOG_DIR"
echo "To check status:  launchctl list | grep claude"
echo "To restart:       launchctl stop com.anthropic.claude-code && launchctl start com.anthropic.claude-code"
echo "To uninstall:     launchctl unload $PLIST_PATH && rm $PLIST_PATH"
