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

async function checkAndInstallEngine(): Promise<void> {
    const isWindows = process.platform === 'win32';
    if (!isWindows) {
        // Auto-installer currently only supports Windows
        return;
    }

    const configPath = vscode.workspace.getConfiguration('neuroshell').get<string>('executablePath');
    
    // Check if executable is custom set
    if (configPath && configPath !== 'NeuroShell' && fs.existsSync(configPath)) {
        return;
    }

    // Check standard installation paths (Local AppData or Program Files)
    const localAppDataPath = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'NeuroShell', 'NeuroShell.exe');
    const programFilesPath = path.join(process.env.ProgramFiles || '', 'NeuroShell', 'NeuroShell.exe');
    const programFilesX86Path = path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'NeuroShell', 'NeuroShell.exe');
    
    let foundPath = '';
    if (fs.existsSync(localAppDataPath)) foundPath = localAppDataPath;
    else if (fs.existsSync(programFilesPath)) foundPath = programFilesPath;
    else if (fs.existsSync(programFilesX86Path)) foundPath = programFilesX86Path;

    if (foundPath) {
        vscode.workspace.getConfiguration('neuroshell').update('executablePath', foundPath, vscode.ConfigurationTarget.Global);
        return;
    }

    // Try to run 'NeuroShell' from PATH
    try {
        cp.execSync('NeuroShell --help', { stdio: 'ignore' });
        return; // It exists in PATH
    } catch (e) {
        // Not found
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
        
        // Target v5.0.0 Release MSI
        const msiUrl = 'https://github.com/abneeshsingh21/neuroshell/releases/download/v5.0.0/NeuroShell-windows-x64-5.0.0.msi';
        const tempPath = path.join(process.env.TEMP || '', 'NeuroShell_Installer.msi');

        await new Promise<void>((resolve, reject) => {
            const file = fs.createWriteStream(tempPath);
            const request = (url: string) => {
                https.get(url, (response) => {
                    if (response.statusCode === 301 || response.statusCode === 302) {
                        return request(response.headers.location as string);
                    }
                    if (response.statusCode !== 200) {
                        reject(new Error(`Failed to download. Make sure the v5.0.0 GitHub release is published! (Status: ${response.statusCode})`));
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
                    vscode.window.showInformationMessage('NeuroShell installed successfully!');
                    
                    const localPath = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'NeuroShell', 'NeuroShell.exe');
                    const progPath = path.join(process.env.ProgramFiles || '', 'NeuroShell', 'NeuroShell.exe');
                    const progX86Path = path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'NeuroShell', 'NeuroShell.exe');
                    
                    if (fs.existsSync(localPath)) {
                        vscode.workspace.getConfiguration('neuroshell').update('executablePath', localPath, vscode.ConfigurationTarget.Global);
                    } else if (fs.existsSync(progPath)) {
                        vscode.workspace.getConfiguration('neuroshell').update('executablePath', progPath, vscode.ConfigurationTarget.Global);
                    } else if (fs.existsSync(progX86Path)) {
                        vscode.workspace.getConfiguration('neuroshell').update('executablePath', progX86Path, vscode.ConfigurationTarget.Global);
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
    const neuroPath = vscode.workspace.getConfiguration('neuroshell').get<string>('executablePath') || 'NeuroShell';

    // Windows Injection
    const profilesWindows = config.get<any>('profiles.windows') || {};
    profilesWindows['NeuroShell'] = {
        path: neuroPath,
        args: [],
        icon: "terminal-bash"
    };
    config.update('profiles.windows', profilesWindows, vscode.ConfigurationTarget.Global);
    config.update('defaultProfile.windows', 'NeuroShell', vscode.ConfigurationTarget.Global);

    // Linux/Mac Injection
    const profilesLinux = config.get<any>('profiles.linux') || {};
    profilesLinux['NeuroShell'] = {
        path: neuroPath,
        args: [],
        icon: "terminal-bash"
    };
    config.update('profiles.linux', profilesLinux, vscode.ConfigurationTarget.Global);
    config.update('defaultProfile.linux', 'NeuroShell', vscode.ConfigurationTarget.Global);

    const profilesMac = config.get<any>('profiles.osx') || {};
    profilesMac['NeuroShell'] = {
        path: neuroPath,
        args: [],
        icon: "terminal-bash"
    };
    config.update('profiles.osx', profilesMac, vscode.ConfigurationTarget.Global);
    config.update('defaultProfile.osx', 'NeuroShell', vscode.ConfigurationTarget.Global);
}

export function deactivate() {}
