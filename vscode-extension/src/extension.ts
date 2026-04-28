import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as https from 'https';

export function activate(context: vscode.ExtensionContext) {
    console.log('NeuroShell VS Code Extension is now active.');

    // Check if NeuroShell exists, if not, prompt to download
    checkAndInstallEngine().then(() => {
        injectNeuroShellProfile();
    });

    let disposable = vscode.commands.registerCommand('neuroshell.injectDefaultTerminal', () => {
        injectNeuroShellProfile();
        vscode.window.showInformationMessage('NeuroShell has been set as your default integrated terminal.');
    });

    context.subscriptions.push(disposable);
}

/**
 * Locate the NeuroShell CLI executable on the system.
 * Returns the full path if found, or empty string if not.
 */
function findNeuroShellCLI(): string {
    const isWindows = process.platform === 'win32';
    if (!isWindows) { return ''; }

    // Check standard installation paths
    const searchDirs = [
        path.join(process.env.LOCALAPPDATA || '', 'Programs', 'NeuroShell'),
        path.join(process.env.ProgramFiles || '', 'NeuroShell'),
        path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'NeuroShell'),
    ];

    for (const dir of searchDirs) {
        // We MUST use the CLI version for the terminal
        const cliExe = path.join(dir, 'NeuroShell-CLI.exe');
        if (fs.existsSync(cliExe)) {
            return cliExe;
        }
    }

    return '';
}

/**
 * Locate python + main.py as a fallback terminal command.
 * Returns { pythonPath, mainPyPath } if found.
 */
function findPythonFallback(): { pythonPath: string; mainPyPath: string } | null {
    // Check common locations for the neuroshell source
    const possibleRoots = [
        // Workspace folders
        ...(vscode.workspace.workspaceFolders?.map(f => f.uri.fsPath) || []),
    ];

    for (const root of possibleRoots) {
        // Look for the CLI entry point, NOT main.py (which starts the GUI)
        const cliPy = path.join(root, 'neuroshell_cli.py');
        if (fs.existsSync(cliPy)) {
            // Find python
            for (const py of ['python', 'python3', 'py']) {
                try {
                    cp.execSync(`${py} --version`, { stdio: 'ignore' });
                    return { pythonPath: py, mainPyPath: cliPy };
                } catch (e) {
                    // Try next
                }
            }
        }
    }

    return null;
}

async function checkAndInstallEngine(): Promise<void> {
    const isWindows = process.platform === 'win32';
    if (!isWindows) {
        // Auto-installer currently only supports Windows
        return;
    }

    let configPath = vscode.workspace.getConfiguration('neuroshell').get<string>('executablePath');
    
    // Auto-migrate from old GUI executable to CLI executable if necessary
    if (configPath && configPath.toLowerCase().endsWith('neuroshell.exe')) {
        const cliPath = path.join(path.dirname(configPath), 'NeuroShell-CLI.exe');
        if (fs.existsSync(cliPath)) {
            configPath = cliPath;
            vscode.workspace.getConfiguration('neuroshell').update('executablePath', cliPath, vscode.ConfigurationTarget.Global);
        }
    }

    // Check if executable is custom set
    if (configPath && configPath !== 'NeuroShell' && configPath !== 'NeuroShell-CLI' && fs.existsSync(configPath)) {
        if (!configPath.toLowerCase().endsWith('neuroshell.exe')) {
            return;
        }
    }

    // Check standard installation paths
    const foundPath = findNeuroShellCLI();
    if (foundPath) {
        vscode.workspace.getConfiguration('neuroshell').update('executablePath', foundPath, vscode.ConfigurationTarget.Global);
        return;
    }

    // Try to run 'NeuroShell-CLI' from PATH
    try {
        cp.execSync('NeuroShell-CLI --help', { stdio: 'ignore' });
        return; // It exists in PATH
    } catch (e) {
        // Not found
    }

    // Check if we have a python fallback (development mode)
    const fallback = findPythonFallback();
    if (fallback) {
        // Dev mode — don't prompt install, just use python
        return;
    }

    // Prompt user to install
    const selection = await vscode.window.showInformationMessage(
        'NeuroShell engine not found on this system. Would you like to automatically download and install it?',
        'Install Now', 'Later'
    );

    if (selection === 'Install Now') {
        await downloadAndInstallMSI();
    }
}

async function downloadAndInstallMSI() {
    return vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: "Installing NeuroShell Engine",
        cancellable: false
    }, async (progress) => {
        progress.report({ message: 'Downloading installer from GitHub...' });
        
        // v5.0.6 Release MSI from neuroshell-installer repo
        const msiUrl = 'https://github.com/abneeshsingh21/neuroshell-installer/releases/download/v5.0.6/NeuroShell-windows-x64-5.0.6.msi';
        const tempPath = path.join(process.env.TEMP || '', 'NeuroShell_Installer.msi');

        await new Promise<void>((resolve, reject) => {
            const file = fs.createWriteStream(tempPath);
            const request = (url: string) => {
                https.get(url, (response) => {
                    if (response.statusCode === 301 || response.statusCode === 302) {
                        return request(response.headers.location as string);
                    }
                    if (response.statusCode !== 200) {
                        reject(new Error(`Failed to download. Status: ${response.statusCode}`));
                        return;
                    }
                    response.pipe(file);
                    file.on('finish', () => {
                        file.close();
                        resolve();
                    });
                }).on('error', (err) => {
                    fs.unlink(tempPath, () => {});
                    reject(err);
                });
            };
            request(msiUrl);
        });

        progress.report({ message: 'Opening Windows Installer...' });
        
        // Execute MSI interactively
        return new Promise<void>((resolve, reject) => {
            cp.exec(`msiexec /i "${tempPath}"`, (error) => {
                if (error) {
                    vscode.window.showErrorMessage('NeuroShell installation was cancelled or failed.');
                    reject(error);
                } else {
                    vscode.window.showInformationMessage('NeuroShell installed successfully! Restart the terminal to use it.');
                    
                    const foundPath = findNeuroShellCLI();
                    if (foundPath) {
                        vscode.workspace.getConfiguration('neuroshell').update('executablePath', foundPath, vscode.ConfigurationTarget.Global);
                    }
                    
                    injectNeuroShellProfile();
                    resolve();
                }
            });
        });
    });
}

function injectNeuroShellProfile() {
    const config = vscode.workspace.getConfiguration('terminal.integrated');
    let neuroPath = vscode.workspace.getConfiguration('neuroshell').get<string>('executablePath') || 'NeuroShell-CLI';

    // Auto-migrate in memory just in case settings haven't synced
    if (neuroPath.toLowerCase().endsWith('neuroshell.exe')) {
        const cliPath = path.join(path.dirname(neuroPath), 'NeuroShell-CLI.exe');
        if (fs.existsSync(cliPath)) {
            neuroPath = cliPath;
        }
    }

    // Determine terminal command and args
    let terminalPath: string;
    let terminalArgs: string[];

    const isWindows = process.platform === 'win32';

    if (neuroPath !== 'NeuroShell-CLI' && neuroPath !== 'NeuroShell' && fs.existsSync(neuroPath)) {
        if (neuroPath.toLowerCase().endsWith('neuroshell.exe')) {
            // NEVER inject the GUI app into the terminal. Force fallback.
            const fallback = findPythonFallback();
            if (fallback) {
                terminalPath = fallback.pythonPath;
                terminalArgs = ['-u', fallback.mainPyPath];
            } else {
                terminalPath = 'NeuroShell-CLI';
                terminalArgs = [];
            }
        } else {
            // Use compiled CLI exe
            terminalPath = neuroPath;
            terminalArgs = [];
        }
    } else {
        // Fallback: use python + main.py from workspace
        const fallback = findPythonFallback();
        if (fallback) {
            terminalPath = fallback.pythonPath;
            terminalArgs = ['-u', fallback.mainPyPath];
        } else {
            // Last resort: try 'NeuroShell-CLI' from PATH
            terminalPath = 'NeuroShell-CLI';
            terminalArgs = [];
        }
    }

    if (isWindows) {
        // Windows Injection
        const profilesWindows = config.get<any>('profiles.windows') || {};
        profilesWindows['NeuroShell'] = {
            path: terminalPath,
            args: terminalArgs,
            icon: "terminal-bash"
        };
        config.update('profiles.windows', profilesWindows, vscode.ConfigurationTarget.Global);
        config.update('defaultProfile.windows', 'NeuroShell', vscode.ConfigurationTarget.Global);
    }

    // Linux/Mac Injection
    const profilesLinux = config.get<any>('profiles.linux') || {};
    profilesLinux['NeuroShell'] = {
        path: terminalPath,
        args: terminalArgs,
        icon: "terminal-bash"
    };
    config.update('profiles.linux', profilesLinux, vscode.ConfigurationTarget.Global);
    config.update('defaultProfile.linux', 'NeuroShell', vscode.ConfigurationTarget.Global);

    const profilesMac = config.get<any>('profiles.osx') || {};
    profilesMac['NeuroShell'] = {
        path: terminalPath,
        args: terminalArgs,
        icon: "terminal-bash"
    };
    config.update('profiles.osx', profilesMac, vscode.ConfigurationTarget.Global);
    config.update('defaultProfile.osx', 'NeuroShell', vscode.ConfigurationTarget.Global);
}

export function deactivate() {}
