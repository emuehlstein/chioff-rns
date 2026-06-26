#!/bin/bash
# chioff-rns tmux session
# Usage: ./scripts/tmux-session.sh [attach]
#
# Windows:
#   0: rnsd logs
#   1: lxmd logs
#   2: nomadnet (TUI)
#   3: shell

SESSION="rns"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running."
  if [ "$1" = "attach" ]; then
    tmux attach -t "$SESSION"
  fi
  exit 0
fi

tmux new-session -d -s "$SESSION" -n "rnsd" \
  "journalctl -fu rnsd.service"

tmux new-window -t "$SESSION" -n "lxmd" \
  "journalctl -fu lxmd.service"

tmux new-window -t "$SESSION" -n "nomadnet" \
  "nomadnet --config /etc/reticulum"

tmux new-window -t "$SESSION" -n "shell"

tmux select-window -t "$SESSION:nomadnet"

if [ "$1" = "attach" ]; then
  tmux attach -t "$SESSION"
fi
