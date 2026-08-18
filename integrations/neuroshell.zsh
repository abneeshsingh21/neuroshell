# NeuroShell Zsh Shell Integration Hook
# Add this line to your ~/.zshrc:
#   source /path/to/neuroshell/integrations/neuroshell.zsh

_neuroshell_translate_widget() {
    local input="$BUFFER"
    if [[ -z "$input" ]]; then
        return
    fi

    # Query NeuroShell IPC Socket via python helper
    local translated
    translated=$(python3 -c "
import socket, json, os, sys
try:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    sock.connect(os.path.expanduser('~/.neuroshell/ipc.sock'))
    req = {'jsonrpc': '2.0', 'method': 'translate', 'params': {'query': sys.argv[1], 'cwd': os.getcwd()}, 'id': 1}
    sock.sendall((json.dumps(req) + '\n').encode())
    data = sock.recv(8192).decode()
    resp = json.loads(data)
    print(resp.get('result', {}).get('command', ''))
except Exception:
    pass
" "$input" 2>/dev/null)

    if [[ -n "$translated" ]]; then
        BUFFER="$translated"
        CURSOR=$#BUFFER
    fi
    zle reset-prompt
}

zle -N _neuroshell_translate_widget
bindkey '^ ' _neuroshell_translate_widget   # Ctrl+Space
bindkey '^[e' _neuroshell_translate_widget  # Alt+E
