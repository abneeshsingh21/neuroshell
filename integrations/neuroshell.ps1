# NeuroShell PowerShell 7 / Windows Terminal Integration Hook
# Add this line to your PowerShell $PROFILE:
#   . "C:\path\to\neuroshell\integrations\neuroshell.ps1"

Set-PSReadLineKeyHandler -Chord 'Alt+Space' -Description 'NeuroShell AI Translation' -ScriptBlock {
    $line = $null
    $cursor = $null
    [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)

    if ([string]::IsNullOrWhiteSpace($line)) {
        return
    }

    try {
        $pipe = New-Object System.IO.Pipes.NamedPipeClientStream(".", "neuroshell_ipc", [System.IO.Pipes.PipeDirection]::InOut)
        $pipe.Connect(1500)
        
        $writer = New-Object System.IO.StreamWriter($pipe)
        $reader = New-Object System.IO.StreamReader($pipe)
        
        $escaped = $line.Replace('\', '\\').Replace('"', '\"')
        $cwd = (Get-Location).Path.Replace('\', '\\').Replace('"', '\"')
        $payload = "{""jsonrpc"":""2.0"",""method"":""translate"",""params"":{""query"":""$escaped"",""cwd"":""$cwd""},""id"":1}`n"
        
        $writer.Write($payload)
        $writer.Flush()
        
        $respRaw = $reader.ReadLine()
        $pipe.Close()

        if ($respRaw) {
            $resp = $respRaw | ConvertFrom-Json
            if ($resp.result -and $resp.result.command) {
                [Microsoft.PowerShell.PSConsoleReadLine]::RevertLine()
                [Microsoft.PowerShell.PSConsoleReadLine]::Insert($resp.result.command)
            }
        }
    } catch {
        # Fallback if IPC pipe is inactive
    }
}
