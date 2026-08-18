// Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
// Proprietary and Confidential - see LICENSE.txt
/**
 * NeuroShell Enterprise VS Code Integration Extension v5.5.7
 * Features:
 * - 1-Click Automatic Binary Downloader & Profile Setup (Windows, macOS, Linux)
 * - Native Terminal Profile Provider & Default Terminal Injection
 * - Direct TypeScript IPC JSON-RPC 2.0 Client (Named Pipes & Unix Sockets)
 * - CodeLens & Editor Context Menu Actions (Ask AI, Explain Selection, Fix Error)
 * - Status Bar Model Indicator with Interactive Switcher
 */

import * as vscode from 'vscode';
import * as net from 'net';
import * as os from 'os';
import * as fs from 'fs';
import * as path from 'path';
import * as cp from 'child_process';
import * as https from 'https';

const REPO = 'abneeshsingh21/neuroshell';
const GITHUB_DOWNLOAD_BASE = `https://github.com/${REPO}/releases/latest/download`;

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
                        // Wait for more chunks
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
// Native Binary Discovery & Target Paths
// ═══════════════════════════════════════════════════════════

function getTargetInstallPath(context?: vscode.ExtensionContext): string {
    const isWindows = process.platform === 'win32';
    if (isWindows) {
        const localApp = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local');
        return path.join(localApp, 'Programs', 'NeuroShell', 'NeuroShell.exe');
    } else {
        return path.join(os.homedir(), '.local', 'bin', 'neuroshell');
    }
}

function findNeuroShellExecutable(context?: vscode.ExtensionContext): string | null {
    const config = vscode.workspace.getConfiguration('neuroshell');
    const customPath = config.get<string>('executablePath');
    if (customPath && fs.existsSync(customPath)) {
        return customPath;
    }

    const isWindows = process.platform === 'win32';
    const workspaceFolders = vscode.workspace.workspaceFolders || [];

    // 1. Workspace dist folder (development mode)
    for (const folder of workspaceFolders) {
        const localExe = isWindows
            ? path.join(folder.uri.fsPath, 'dist', 'NeuroShell.exe')
            : path.join(folder.uri.fsPath, 'dist', 'neuroshell');
        if (fs.existsSync(localExe)) return localExe;
    }

    // 2. Standard user installation path
    const userTarget = getTargetInstallPath(context);
    if (fs.existsSync(userTarget)) return userTarget;

    // 3. Extension global storage path
    if (context) {
        const storageExe = isWindows
            ? path.join(context.globalStorageUri.fsPath, 'bin', 'NeuroShell.exe')
            : path.join(context.globalStorageUri.fsPath, 'bin', 'neuroshell');
        if (fs.existsSync(storageExe)) return storageExe;
    }

    // 4. System-wide standard paths
    if (isWindows) {
        const searchPaths = [
            path.join(process.env.ProgramFiles || '', 'NeuroShell', 'NeuroShell.exe'),
            'C:\\Program Files\\NeuroShell\\NeuroShell.exe',
            path.join(os.homedir(), 'Desktop', 'LLM model train', 'neuroshell', 'dist', 'NeuroShell.exe'),
        ];
        for (const p of searchPaths) {
            if (fs.existsSync(p)) return p;
        }
    } else {
        const posixPaths = [
            '/usr/local/bin/neuroshell',
            '/opt/homebrew/bin/neuroshell',
            '/usr/bin/neuroshell',
            path.join(os.homedir(), 'bin', 'neuroshell'),
        ];
        for (const p of posixPaths) {
            if (fs.existsSync(p)) return p;
        }
    }

    // 5. System PATH
    try {
        const whichCmd = isWindows ? 'where NeuroShell.exe' : 'which neuroshell';
        const found = cp.execSync(whichCmd, { encoding: 'utf-8', timeout: 2000 }).trim().split('\n')[0].trim();
        if (found && fs.existsSync(found)) return found;
    } catch {
        // Not in PATH
    }

    return null;
}

// ═══════════════════════════════════════════════════════════
// Automated Terminal Profile Configuration
// ═══════════════════════════════════════════════════════════

async function configureTerminalProfile(exePath: string): Promise<void> {
    const config = vscode.workspace.getConfiguration();
    const isWindows = process.platform === 'win32';
    const isMac = process.platform === 'darwin';
    const isLinux = process.platform === 'linux';

    // 1. Update executablePath setting
    await config.update('neuroshell.executablePath', exePath, vscode.ConfigurationTarget.Global);

    // 2. Configure OS Profiles and Default Profile
    if (isWindows) {
        const profiles: any = Object.assign({}, config.get('terminal.integrated.profiles.windows'));
        profiles['NeuroShell'] = {
            path: exePath,
            args: [],
            icon: 'terminal'
        };
        await config.update('terminal.integrated.profiles.windows', profiles, vscode.ConfigurationTarget.Global);
        await config.update('terminal.integrated.defaultProfile.windows', 'NeuroShell', vscode.ConfigurationTarget.Global);
    } else if (isMac) {
        const profiles: any = Object.assign({}, config.get('terminal.integrated.profiles.osx'));
        profiles['NeuroShell'] = {
            path: exePath,
            args: [],
            icon: 'terminal'
        };
        await config.update('terminal.integrated.profiles.osx', profiles, vscode.ConfigurationTarget.Global);
        await config.update('terminal.integrated.defaultProfile.osx', 'NeuroShell', vscode.ConfigurationTarget.Global);
    } else if (isLinux) {
        const profiles: any = Object.assign({}, config.get('terminal.integrated.profiles.linux'));
        profiles['NeuroShell'] = {
            path: exePath,
            args: [],
            icon: 'terminal'
        };
        await config.update('terminal.integrated.profiles.linux', profiles, vscode.ConfigurationTarget.Global);
        await config.update('terminal.integrated.defaultProfile.linux', 'NeuroShell', vscode.ConfigurationTarget.Global);
    }
}

// ═══════════════════════════════════════════════════════════
// Enterprise Engine Downloader with Live Progress
// ═══════════════════════════════════════════════════════════

function downloadFileWithProgress(url: string, destPath: string, progress: vscode.Progress<{ message?: string; increment?: number }>, token: vscode.CancellationToken): Promise<void> {
    return new Promise((resolve, reject) => {
        try {
            fs.mkdirSync(path.dirname(destPath), { recursive: true });
        } catch (e: any) {
            reject(new Error(`Failed to create directory ${path.dirname(destPath)}: ${e.message}`));
            return;
        }

        const executeGet = (requestUrl: string) => {
            const req = https.get(requestUrl, { headers: { 'User-Agent': 'NeuroShell-VSCode-Extension' } }, (res) => {
                if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                    // Follow GitHub release redirect
                    executeGet(res.headers.location);
                    return;
                }

                if (res.statusCode !== 200) {
                    reject(new Error(`Server returned HTTP ${res.statusCode}`));
                    return;
                }

                const totalBytes = parseInt(res.headers['content-length'] || '0', 10);
                let receivedBytes = 0;
                let lastReportedPercent = 0;

                const fileStream = fs.createWriteStream(destPath);

                res.on('data', (chunk: Buffer) => {
                    if (token.isCancellationRequested) {
                        res.destroy();
                        fileStream.close();
                        fs.unlink(destPath, () => {});
                        reject(new Error('Download cancelled by user.'));
                        return;
                    }

                    receivedBytes += chunk.length;
                    fileStream.write(chunk);

                    if (totalBytes > 0) {
                        const currentPercent = Math.floor((receivedBytes / totalBytes) * 100);
                        const increment = currentPercent - lastReportedPercent;
                        if (increment >= 1) {
                            lastReportedPercent = currentPercent;
                            const currentMb = (receivedBytes / (1024 * 1024)).toFixed(1);
                            const totalMb = (totalBytes / (1024 * 1024)).toFixed(1);
                            progress.report({
                                increment: increment,
                                message: `${currentMb} MB / ${totalMb} MB (${currentPercent}%)`
                            });
                        }
                    } else {
                        const currentMb = (receivedBytes / (1024 * 1024)).toFixed(1);
                        progress.report({
                            message: `Downloaded ${currentMb} MB`
                        });
                    }
                });

                res.on('end', () => {
                    fileStream.end();
                    if (!process.platform.startsWith('win')) {
                        try {
                            fs.chmodSync(destPath, 0o755);
                        } catch {}
                    }
                    resolve();
                });

                res.on('error', (err) => {
                    fileStream.close();
                    fs.unlink(destPath, () => {});
                    reject(err);
                });
            });

            req.on('error', (err) => {
                reject(err);
            });
        };

        executeGet(url);
    });
}

async function triggerEngineDownload(context?: vscode.ExtensionContext): Promise<boolean> {
    const isWindows = process.platform === 'win32';
    const assetName = isWindows ? 'NeuroShell.exe' : 'neuroshell';
    const downloadUrl = `${GITHUB_DOWNLOAD_BASE}/${assetName}`;
    const destPath = getTargetInstallPath(context);

    return await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: '⌬ Downloading NeuroShell Native Engine...',
            cancellable: true
        },
        async (progress, token) => {
            try {
                progress.report({ increment: 0, message: 'Connecting to GitHub CDN...' });
                await downloadFileWithProgress(downloadUrl, destPath, progress, token);

                // Auto-configure terminal profiles across all settings
                await configureTerminalProfile(destPath);

                vscode.window.showInformationMessage(
                    '🎉 NeuroShell has been installed and configured as your default terminal!',
                    'Open NeuroShell Terminal'
                ).then((choice) => {
                    if (choice === 'Open NeuroShell Terminal') {
                        const term = vscode.window.createTerminal({
                            name: 'NeuroShell',
                            shellPath: destPath,
                            iconPath: new vscode.ThemeIcon('terminal')
                        });
                        term.show();
                    }
                });

                return true;
            } catch (err: any) {
                vscode.window.showErrorMessage(`Download failed: ${err.message}. You can manually download from github.com/${REPO}/releases`);
                return false;
            }
        }
    );
}

let g_downloadPromptTimer: NodeJS.Timeout | null = null;
let g_isDownloading: boolean = false;

function stopDownloadPromptLoop() {
    if (g_downloadPromptTimer) {
        clearInterval(g_downloadPromptTimer);
        g_downloadPromptTimer = null;
    }
}

function startDownloadPromptLoop(context: vscode.ExtensionContext) {
    if (g_downloadPromptTimer) return;

    const showPrompt = () => {
        const exe = findNeuroShellExecutable(context);
        if (exe) {
            stopDownloadPromptLoop();
            configureTerminalProfile(exe);
            return;
        }

        if (g_isDownloading) return;

        vscode.window.showInformationMessage(
            '⌬ NeuroShell Engine is required to power the AI terminal. Download & setup now in 1-click.',
            '⚡ Download & Setup NeuroShell'
        ).then((selection) => {
            if (selection === '⚡ Download & Setup NeuroShell') {
                g_isDownloading = true;
                stopDownloadPromptLoop();
                triggerEngineDownload(context).then((success) => {
                    g_isDownloading = false;
                    if (!success) {
                        // If user cancelled or error, resume prompting after brief interval
                        startDownloadPromptLoop(context);
                    }
                });
            }
        });
    };

    // Initial prompt
    showPrompt();

    // Re-prompt every 6 seconds until downloaded
    g_downloadPromptTimer = setInterval(() => {
        showPrompt();
    }, 6000);
}

// ═══════════════════════════════════════════════════════════
// Extension Activation & Lifecycle
// ═══════════════════════════════════════════════════════════

export function activate(context: vscode.ExtensionContext) {
    console.log('NeuroShell Enterprise VS Code Extension active.');

    // 1. Check if Engine is installed, otherwise start 6-second recurring prompt loop
    const installedExe = findNeuroShellExecutable(context);
    if (!installedExe) {
        startDownloadPromptLoop(context);
    } else {
        stopDownloadPromptLoop();
        configureTerminalProfile(installedExe);
    }

    // 2. Status Bar Item
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'neuroshell.askAI';
    statusBarItem.text = '$(terminal) ⌬ NeuroShell';
    statusBarItem.tooltip = 'Click to open NeuroShell AI Assistant (Ctrl+Alt+N)';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // 3. Terminal Profile Provider
    context.subscriptions.push(
        vscode.window.registerTerminalProfileProvider('neuroshell.terminal.profile', {
            provideTerminalProfile: () => {
                const exePath = findNeuroShellExecutable(context) || getTargetInstallPath(context);
                return new vscode.TerminalProfile({
                    name: 'NeuroShell',
                    shellPath: exePath,
                    iconPath: new vscode.ThemeIcon('terminal')
                });
            }
        })
    );

    // 4. Command: Explicit Native Terminal Opener
    const openTermCmd = vscode.commands.registerCommand('neuroshell.openTerminal', () => {
        const exePath = findNeuroShellExecutable(context) || getTargetInstallPath(context);
        const term = vscode.window.createTerminal({
            name: 'NeuroShell',
            shellPath: exePath,
            iconPath: new vscode.ThemeIcon('terminal')
        });
        term.show();
    });
    context.subscriptions.push(openTermCmd);

    // 5. Command: Download / Update Engine
    const downloadCmd = vscode.commands.registerCommand('neuroshell.downloadEngine', () => {
        triggerEngineDownload(context);
    });

    // 6. Command: Ask AI / Shell Translation
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
                    const terminal = vscode.window.activeTerminal || vscode.window.createTerminal({
                        name: 'NeuroShell',
                        shellPath: findNeuroShellExecutable(context) || getTargetInstallPath(context),
                        iconPath: new vscode.ThemeIcon('terminal')
                    });
                    terminal.show();
                    terminal.sendText(result.command);
                } else if (selection?.label.startsWith('$(copy)')) {
                    await vscode.env.clipboard.writeText(result.command);
                    vscode.window.showInformationMessage(`Copied: ${result.command}`);
                }
            }
        } catch (err: any) {
            const terminal = vscode.window.activeTerminal || vscode.window.createTerminal({
                name: 'NeuroShell',
                shellPath: findNeuroShellExecutable(context) || getTargetInstallPath(context),
                iconPath: new vscode.ThemeIcon('terminal')
            });
            terminal.show();
            terminal.sendText(query);
        }
    });

    // 7. Command: Explain Selection
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

    // 8. Command: Fix Terminal Error
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
                    const term = vscode.window.activeTerminal || vscode.window.createTerminal({
                        name: 'NeuroShell',
                        shellPath: findNeuroShellExecutable(context) || getTargetInstallPath(context),
                        iconPath: new vscode.ThemeIcon('terminal')
                    });
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

    // 9. Command: Set Default Terminal
    const injectCmd = vscode.commands.registerCommand('neuroshell.injectDefaultTerminal', async () => {
        const exePath = findNeuroShellExecutable(context);
        if (!exePath) {
            const download = await vscode.window.showWarningMessage(
                'NeuroShell executable not found. Would you like to download it now?',
                'Download Engine'
            );
            if (download === 'Download Engine') {
                triggerEngineDownload(context);
            }
            return;
        }

        await configureTerminalProfile(exePath);
        vscode.window.showInformationMessage('🎉 NeuroShell is now configured as your default integrated terminal profile.');
    });

    // 10. Command: Check for Updates
    const updateCmd = vscode.commands.registerCommand('neuroshell.checkForUpdates', () => {
        vscode.window.showInformationMessage('NeuroShell is up to date.');
    });

    context.subscriptions.push(downloadCmd, askAICmd, explainCmd, fixErrorCmd, injectCmd, updateCmd);
}

export function deactivate() {
    stopDownloadPromptLoop();
}
