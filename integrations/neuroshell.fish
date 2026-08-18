# NeuroShell Fish Integration Hook
# Add this line to your ~/.config/fish/config.fish:
#   source /path/to/neuroshell/integrations/neuroshell.fish

function neuroshell_translate_widget
    set -l input (commandline)
    if test -z "$input"
        return
    end

    set -l translated (python3 -c "
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

    if test -n "$translated"
        commandline -r "$translated"
    end
end

bind \cg neuroshell_translate_widget
bind \e\x20 neuroshell_translate_widget # Alt+Space
