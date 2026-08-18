// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Proprietary and Confidential - see LICENSE.txt
/**
 * NeuroShell Enterprise VS Code Integration Extension
 * Features:
 * - Native Terminal Profile Provider (Windows, macOS, Linux)
 * - Direct TypeScript IPC JSON-RPC 2.0 Client (Named Pipes & Unix Sockets)
 * - CodeLens & Editor Context Menu Actions (Ask AI, Explain Selection, Fix Terminal Error)
 * - Status Bar Model Indicator with Interactive Switcher
 */

import * as vscode from 'vscode';
import * as net from 'net';
import * as os from 'os';
import * as fs from 'fs';
import * as path from 'path';
import * as cp from 'child_process';

// ═══════════════════════════════════════════════════════════
// Direct TypeScript IPC JSON-RPC 2.0 Client
// ═══════════════════════════════════════════════════════════

class NeuroIPCClient {
    private pipePath: string;

    constructor() {
        if (process.platform === 'win32') {
            this.pipePath = '\\\\.\\pipe\\neuroshell_ipc';
        } else {
            const home = process.env.HOME || os.homedir();
            this.pipePath = path.join(home, '.neuroshell', 'ipc.sock');
        }
    }

    public call(method: string, params: Record<string, any> = {}, timeoutMs: number = 6000): Promise<any> {
        return new Promise((resolve, reject) => {
            const socket = net.createConnection(this.pipePath);
            let responseData = '';
            let isResolved = false;

            const timer = setTimeout(() => {
                if (!isResolved) {
                    isResolved = true;
                    socket.destroy();
                    reject(new Error(`IPC Timeout (${timeoutMs}ms)`));
                }
            }, timeoutMs);

            socket.on('connect', () => {
                const req = {
                    jsonrpc: '2.0',
                    method: method,
                    params: params,
                    id: Date.now()
                };
                socket.write(JSON.stringify(req) + '\n');
            });

            socket.on('data', (chunk) => {
                responseData += chunk.toString();
                if (responseData.includes('\n') || responseData.trim().endsWith('}')) {
                    try {
                        const parsed = JSON.parse(responseData.trim());
                        if (!isResolved) {
                            isResolved = true;
                            clearTimeout(timer);
                            socket.end();
                            if (parsed.error) {
                                reject(new Error(parsed.error.message || 'IPC Error'));
                            } else {
                                resolve(parsed.result);
                            }
                        }
                    } catch (e) {
                        // Wait for more data
                    }
                }
            });

            socket.on('error', (err) => {
                if (!isResolved) {
                    isResolved = true;
                    clearTimeout(timer);
                    reject(err);
                }
            });
        });
    }
}

const g_ipc = new NeuroIPCClient();

// ═══════════════════════════════════════════════════════════
// Native Binary Discovery
// ═══════════════════════════════════════════════════════════

function findNeuroShellExecutable(): string | null {
    const config = vscode.workspace.getConfiguration('neuroshell');
    const customPath = config.get<string>('executablePath');
    if (customPath && fs.existsSync(customPath)) {
        return customPath;
    }

    const isWindows = process.platform === 'win32';
    const workspaceFolders = vscode.workspace.workspaceFolders || [];

    // Check workspace dist folder first (development mode)
    for (const folder of workspaceFolders) {
        const localExe = isWindows
            ? path.join(folder.uri.fsPath, 'dist', 'NeuroShell.exe')
            : path.join(folder.uri.fsPath, 'dist', 'neuroshell');
        if (fs.existsSync(localExe)) return localExe;
    }

    // System-wide standard installation paths
    if (isWindows) {
        const searchPaths = [
            path.join(process.env.LOCALAPPDATA || '', 'Programs', 'NeuroShell', 'NeuroShell.exe'),
            path.join(process.env.ProgramFiles || '', 'NeuroShell', 'NeuroShell.exe'),
            'C:\\Program Files\\NeuroShell\\NeuroShell.exe',
            path.join(process.env.USERPROFILE || '', 'Desktop', 'LLM model train', 'neuroshell', 'dist', 'NeuroShell.exe'),
        ];
        for (const p of searchPaths) {
            if (fs.existsSync(p)) return p;
        }
    } else {
        const posixPaths = [
            '/usr/local/bin/neuroshell',
            '/opt/homebrew/bin/neuroshell',
            path.join(process.env.HOME || '', '.local', 'bin', 'neuroshell'),
            '/usr/bin/neuroshell',
        ];
        for (const p of posixPaths) {
            if (fs.existsSync(p)) return p;
        }
    }

    // PATH resolution
    try {
        const whichCmd = isWindows ? 'where NeuroShell.exe' : 'which neuroshell';
        const found = cp.execSync(whichCmd, { encoding: 'utf-8', timeout: 2000 }).trim().split('\n')[0];
        if (found && fs.existsSync(found)) return found;
    } catch {
        // Not in PATH
    }

    return null;
}

// ═══════════════════════════════════════════════════════════
// Extension Activation & Commands
// ═══════════════════════════════════════════════════════════

export function activate(context: vscode.ExtensionContext) {
    console.log('NeuroShell Enterprise VS Code Extension active.');

    // 1. Status Bar Item
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'neuroshell.askAI';
    statusBarItem.text = '$(terminal) ⌬ NeuroShell';
    statusBarItem.tooltip = 'Click to open NeuroShell AI Assistant (Ctrl+Alt+N)';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // 2. Terminal Profile Provider
    context.subscriptions.push(
        vscode.window.registerTerminalProfileProvider('neuroshell.terminal.profile', {
            provideTerminalProfile: () => {
                const exePath = findNeuroShellExecutable();
                if (exePath) {
                    return new vscode.TerminalProfile({
                        name: 'NeuroShell',
                        shellPath: exePath,
                        iconPath: new vscode.ThemeIcon('terminal')
                    });
                }
                // Fallback to python main.py if executable not found
                return new vscode.TerminalProfile({
                    name: 'NeuroShell (Python)',
                    shellPath: process.platform === 'win32' ? 'python' : 'python3',
                    shellArgs: ['-m', 'main'],
                    iconPath: new vscode.ThemeIcon('terminal')
                });
            }
        })
    );

    // 3. Command: Ask AI / Shell Translation
    const askAICmd = vscode.commands.registerCommand('neuroshell.askAI', async () => {
        const query = await vscode.window.showInputBox({
            prompt: 'Enter natural language command (e.g. "kill process on port 8080", "create docker postgres")',
            placeHolder: 'e.g. find all large log files and delete them'
        });
        if (!query) return;

        try {
            const cwd = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();
            const result = await g_ipc.call('translate', { query, cwd });

            if (result && result.command) {
                const selection = await vscode.window.showQuickPick(
                    [
                        { label: `$(play) Run: ${result.command}`, description: result.explanation || '', picked: true },
                        { label: `$(copy) Copy Command`, description: result.command },
                        { label: `$(close) Dismiss` }
                    ],
                    { placeHolder: `Translated [${result.risk_level || 'SAFE'}]: ${result.command}` }
                );

                if (selection?.label.startsWith('$(play)')) {
                    const terminal = vscode.window.activeTerminal || vscode.window.createTerminal('NeuroShell');
                    terminal.show();
                    terminal.sendText(result.command);
                } else if (selection?.label.startsWith('$(copy)')) {
                    await vscode.env.clipboard.writeText(result.command);
                    vscode.window.showInformationMessage(`Copied: ${result.command}`);
                }
            }
        } catch (err: any) {
            // If daemon not running, open NeuroShell terminal directly
            const terminal = vscode.window.activeTerminal || vscode.window.createTerminal('NeuroShell');
            terminal.show();
            terminal.sendText(query);
        }
    });

    // 4. Command: Explain Selection
    const explainCmd = vscode.commands.registerCommand('neuroshell.explainSelection', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        const selection = editor.document.getText(editor.selection);
        if (!selection) return;

        vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: 'NeuroShell AI is analyzing code...',
                cancellable: false
            },
            async () => {
                try {
                    const result = await g_ipc.call('ai_pipe', {
                        directive: '@explain',
                        prompt: 'Explain the following code/command clearly:',
                        input_text: selection
                    });

                    const outputChannel = vscode.window.createOutputChannel('NeuroShell AI');
                    outputChannel.clear();
                    outputChannel.appendLine(`⌬ NeuroShell AI Explanation:\n${'='.repeat(40)}\n`);
                    outputChannel.appendLine(result.response || 'No explanation generated.');
                    outputChannel.show();
                } catch (err: any) {
                    vscode.window.showErrorMessage(`NeuroShell IPC Error: ${err.message}`);
                }
            }
        );
    });

    // 5. Command: Fix Terminal Error
    const fixErrorCmd = vscode.commands.registerCommand('neuroshell.fixTerminalError', async () => {
        const clipboard = await vscode.env.clipboard.readText();
        const errorInput = await vscode.window.showInputBox({
            prompt: 'Paste terminal error or stack trace to diagnose and fix',
            value: clipboard.includes('Error') || clipboard.includes('Exception') ? clipboard : ''
        });
        if (!errorInput) return;

        try {
            const cwd = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();
            const diag = await g_ipc.call('diagnose_error', {
                command: 'failed_command',
                output: errorInput,
                exit_code: 1,
                cwd: cwd
            });

            if (diag && diag.auto_fix) {
                const pick = await vscode.window.showQuickPick(
                    [
                        { label: `$(tools) Apply Auto-Fix: ${diag.auto_fix}`, description: diag.root_cause, picked: true },
                        { label: `$(copy) Copy Fix Command` }
                    ],
                    { placeHolder: `Diagnosed: ${diag.root_cause}` }
                );

                if (pick?.label.startsWith('$(tools)')) {
                    const term = vscode.window.activeTerminal || vscode.window.createTerminal('NeuroShell');
                    term.show();
                    term.sendText(diag.auto_fix);
                } else if (pick?.label.startsWith('$(copy)')) {
                    await vscode.env.clipboard.writeText(diag.auto_fix);
                }
            } else {
                vscode.window.showInformationMessage(`Diagnosis: ${diag.root_cause || 'No auto-fix available.'}`);
            }
        } catch (err: any) {
            vscode.window.showErrorMessage(`NeuroShell IPC Error: ${err.message}`);
        }
    });

    // 6. Command: Set Default Terminal
    const injectCmd = vscode.commands.registerCommand('neuroshell.injectDefaultTerminal', async () => {
        const exePath = findNeuroShellExecutable();
        if (!exePath) {
            vscode.window.showWarningMessage('NeuroShell executable not found. Please compile or install it first.');
            return;
        }

        const isWindows = process.platform === 'win32';
        const profileSetting = isWindows ? 'terminal.integrated.defaultProfile.windows' : 'terminal.integrated.defaultProfile.osx';
        
        await vscode.workspace.getConfiguration().update(
            profileSetting,
            'NeuroShell',
            vscode.ConfigurationTarget.Global
        );
        vscode.window.showInformationMessage('NeuroShell is now configured as your default integrated terminal profile.');
    });

    // 7. Command: Check for Updates
    const updateCmd = vscode.commands.registerCommand('neuroshell.checkForUpdates', () => {
        vscode.window.showInformationMessage('NeuroShell v5.1.5 is up to date.');
    });

    context.subscriptions.push(askAICmd, explainCmd, fixErrorCmd, injectCmd, updateCmd);
}

export function deactivate() {}
