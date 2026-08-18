# NeuroShell Bash Integration Hook (Bash 4.4+)
# Add this line to your ~/.bashrc:
#   source /path/to/neuroshell/integrations/neuroshell.bash

_neuroshell_bash_translate() {
    local input="$READLINE_LINE"
    if [[ -z "$input" ]]; then
        return
    fi

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
        READLINE_LINE="$translated"
        READLINE_POINT=${#READLINE_LINE}
    fi
}

# Bind to Ctrl+Space in Bash
bind -x '"\C-@": _neuroshell_bash_translate'
