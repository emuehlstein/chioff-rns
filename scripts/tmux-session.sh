#!/bin/bash
# chioff-rns tmux session
# Usage: ./scripts/tmux-session.sh [attach]
SESSION="rns"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running."
  [ "$1" = "attach" ] && tmux attach -t "$SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" -n rnsd
tmux send-keys -t "$SESSION:rnsd" "journalctl -fu rnsd.service" Enter

tmux new-window -t "$SESSION:" -n lxmd
tmux send-keys -t "$SESSION:lxmd" "journalctl -fu lxmd.service" Enter

tmux new-window -t "$SESSION:" -n nomadnet
tmux send-keys -t "$SESSION:nomadnet" "journalctl -fu nomadnet.service" Enter

tmux new-window -t "$SESSION:" -n shell
tmux select-window -t "$SESSION:nomadnet"

[ "$1" = "attach" ] && tmux attach -t "$SESSION"
