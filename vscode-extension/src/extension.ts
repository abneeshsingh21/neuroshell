import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import * as https from 'https';

// ═══════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════

const INSTALLER_REPO = 'abneeshsingh21/neuroshell-installer';
const GITHUB_API_LATEST = `https://api.github.com/repos/${INSTALLER_REPO}/releases/latest`;
const VERSION_STATE_KEY = 'neuroshell.installedVersion';
const LAST_CHECK_KEY = 'neuroshell.lastUpdateCheck';
const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000; // Check every 6 hours

export function activate(context: vscode.ExtensionContext) {
    console.log('NeuroShell VS Code Extension is now active.');

    // Check if NeuroShell exists, if not, prompt to download
    checkAndInstallEngine(context).then(() => {
        injectNeuroShellProfile();
        // After initial setup, check for updates in background
        checkForUpdates(context, false);
    });

    // Command: Inject terminal profile
    let injectCmd = vscode.commands.registerCommand('neuroshell.injectDefaultTerminal', () => {
        injectNeuroShellProfile();
        vscode.window.showInformationMessage('NeuroShell has been set as your default integrated terminal.');
    });

    // Command: Manual update check
    let updateCmd = vscode.commands.registerCommand('neuroshell.checkForUpdates', () => {
        checkForUpdates(context, true);
    });

    context.subscriptions.push(injectCmd, updateCmd);
}


// ═══════════════════════════════════════════════════════════
// Python Fallback (dev mode)
// ═══════════════════════════════════════════════════════════

/**
 * Locate python + neuroshell_cli.py in the current workspace.
 * This is the FASTEST way to start NeuroShell (no exe validation needed).
 * Returns { pythonPath, mainPyPath } if found.
 */
function findPythonFallback(): { pythonPath: string; mainPyPath: string } | null {
    const possibleRoots = [
        ...(vscode.workspace.workspaceFolders?.map(f => f.uri.fsPath) || []),
    ];

    for (const root of possibleRoots) {
        // Look for the CLI entry point, NOT main.py (which starts the GUI)
        const cliPy = path.join(root, 'neuroshell_cli.py');
        if (fs.existsSync(cliPy)) {
            // Find python
            for (const py of ['python', 'python3', 'py']) {
                try {
                    cp.execSync(`${py} --version`, { stdio: 'ignore', timeout: 3000 });
                    return { pythonPath: py, mainPyPath: cliPy };
                } catch (e) {
                    // Try next
                }
            }
        }
    }

    return null;
}


// ═══════════════════════════════════════════════════════════
// Exe Discovery
// ═══════════════════════════════════════════════════════════

/**
 * Locate the NeuroShell CLI executable on the system.
 * Only checks file existence — no slow validation.
 * Returns the full path if found, or empty string if not.
 */
function findNeuroShellCLI(): string {
    const isWindows = process.platform === 'win32';
    
    if (isWindows) {
        const searchDirs = [
            path.join(process.env.LOCALAPPDATA || '', 'Programs', 'NeuroShell'),
            path.join(process.env.ProgramFiles || '', 'NeuroShell'),
            path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'NeuroShell'),
        ];

        for (const dir of searchDirs) {
            const cliExe = path.join(dir, 'NeuroShell-CLI.exe');
            if (fs.existsSync(cliExe)) {
                return cliExe;
            }
        }
    } else {
        // Linux/macOS
        const searchPaths = [
            '/usr/local/bin/neuroshell',
            '/usr/bin/neuroshell'
        ];
        
        for (const bin of searchPaths) {
            if (fs.existsSync(bin)) {
                return bin;
            }
        }
    }

    return '';
}

/**
 * Get the install directory for the exe (prefers AppData, falls back to Program Files).
 */
function getInstallDir(): string {
    // Try Program Files first
    const progDir = path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'NeuroShell');
    try {
        if (!fs.existsSync(progDir)) {
            fs.mkdirSync(progDir, { recursive: true });
        }
        // Test write access
        const testFile = path.join(progDir, '.write_test');
        fs.writeFileSync(testFile, 'test');
        fs.unlinkSync(testFile);
        return progDir;
    } catch (e) {
        // Fall back to AppData
        const appDataDir = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'NeuroShell');
        if (!fs.existsSync(appDataDir)) {
            fs.mkdirSync(appDataDir, { recursive: true });
        }
        return appDataDir;
    }
}


// ═══════════════════════════════════════════════════════════
// Auto-Update System
// ═══════════════════════════════════════════════════════════

interface GitHubRelease {
    tag_name: string;
    assets: Array<{
        name: string;
        browser_download_url: string;
        size: number;
    }>;
}

/**
 * Fetch the latest release info from GitHub API.
 */
function fetchLatestRelease(): Promise<GitHubRelease> {
    return new Promise((resolve, reject) => {
        const options = {
            headers: {
                'User-Agent': 'NeuroShell-VSCode-Extension',
                'Accept': 'application/vnd.github.v3+json'
            }
        };

        https.get(GITHUB_API_LATEST, options, (res) => {
            if (res.statusCode === 301 || res.statusCode === 302) {
                https.get(res.headers.location!, options, (res2) => {
                    let data = '';
                    res2.on('data', chunk => data += chunk);
                    res2.on('end', () => {
                        try { resolve(JSON.parse(data)); }
                        catch (e) { reject(new Error('Failed to parse release data')); }
                    });
                }).on('error', reject);
                return;
            }

            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try { resolve(JSON.parse(data)); }
                catch (e) { reject(new Error('Failed to parse release data')); }
            });
        }).on('error', reject);
    });
}

/**
 * Compare two semver-style version tags (e.g., "v5.1.0" vs "v5.0.9").
 * Returns true if remote is newer than local.
 */
function isNewerVersion(local: string, remote: string): boolean {
    const parse = (v: string) => v.replace(/^v/, '').split('.').map(Number);
    const localParts = parse(local);
    const remoteParts = parse(remote);

    for (let i = 0; i < 3; i++) {
        const l = localParts[i] || 0;
        const r = remoteParts[i] || 0;
        if (r > l) { return true; }
        if (r < l) { return false; }
    }
    return false;
}

/**
 * Check for updates and auto-install if a newer version is available.
 * @param manual If true, always check (ignore cooldown) and show messages.
 */
async function checkForUpdates(context: vscode.ExtensionContext, manual: boolean) {
    // Skip update check for dev mode (Python fallback)
    const fallback = findPythonFallback();
    if (fallback && !manual) {
        return;
    }

    // Throttle automatic checks to every 6 hours
    if (!manual) {
        const lastCheck = context.globalState.get<number>(LAST_CHECK_KEY, 0);
        if (Date.now() - lastCheck < CHECK_INTERVAL_MS) {
            return;
        }
    }

    try {
        // Record check time
        context.globalState.update(LAST_CHECK_KEY, Date.now());

        const release = await fetchLatestRelease();
        const remoteVersion = release.tag_name; // e.g., "v5.1.0"
        const localVersion = context.globalState.get<string>(VERSION_STATE_KEY, 'v0.0.0');

        if (!isNewerVersion(localVersion, remoteVersion)) {
            if (manual) {
                vscode.window.showInformationMessage(`NeuroShell is up to date (${localVersion}).`);
            }
            return;
        }

        const isWindows = process.platform === 'win32';

        if (!isWindows) {
            // For Linux/macOS, just notify the user and don't try to auto-download exe
            if (manual) {
                vscode.window.showInformationMessage(`NeuroShell ${remoteVersion} is available (you have ${localVersion}). Run the curl install script to upgrade.`);
            } else {
                vscode.window.showInformationMessage(`NeuroShell update ${remoteVersion} is available! Run: curl -sSL https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.sh | bash`);
            }
            return;
        }

        // Find the exe asset for Windows
        const exeAsset = release.assets.find(a => a.name.toLowerCase().endsWith('.exe'));
        if (!exeAsset) {
            if (manual) {
                vscode.window.showWarningMessage('No exe found in the latest release.');
            }
            return;
        }

        const sizeMB = (exeAsset.size / (1024 * 1024)).toFixed(0);

        // For automatic updates, ask the user first
        if (!manual) {
            const choice = await vscode.window.showInformationMessage(
                `NeuroShell ${remoteVersion} is available (you have ${localVersion}). Update now? (~${sizeMB}MB)`,
                'Update Now', 'Later'
            );
            if (choice !== 'Update Now') {
                return;
            }
        } else {
            const choice = await vscode.window.showInformationMessage(
                `NeuroShell ${remoteVersion} available (you have ${localVersion}). Download ~${sizeMB}MB?`,
                'Update', 'Cancel'
            );
            if (choice !== 'Update') {
                return;
            }
        }

        // Download and install the update
        await downloadUpdate(context, exeAsset.browser_download_url, remoteVersion);

    } catch (err: any) {
        if (manual) {
            vscode.window.showErrorMessage(`Update check failed: ${err.message}`);
        }
        console.error('NeuroShell update check failed:', err);
    }
}

/**
 * Download the new exe, delete the old one, and update the config.
 */
async function downloadUpdate(context: vscode.ExtensionContext, downloadUrl: string, version: string) {
    return vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: `Updating NeuroShell to ${version}`,
        cancellable: false
    }, async (progress) => {
        const installDir = getInstallDir();
        const exePath = path.join(installDir, 'NeuroShell-CLI.exe');
        const tempPath = path.join(installDir, 'NeuroShell-CLI.exe.update');

        progress.report({ message: `Downloading (~500MB)...` });

        try {
            // Download to temp file first (atomic update)
            await downloadFile(downloadUrl, tempPath, progress);

            // Delete old exe
            if (fs.existsSync(exePath)) {
                try {
                    fs.unlinkSync(exePath);
                } catch (e) {
                    // If can't delete (in use), rename it for cleanup later
                    const oldPath = path.join(installDir, 'NeuroShell-CLI.exe.old');
                    try { fs.unlinkSync(oldPath); } catch (_) {}
                    fs.renameSync(exePath, oldPath);
                }
            }

            // Move temp to final path
            fs.renameSync(tempPath, exePath);

            // Update stored version
            context.globalState.update(VERSION_STATE_KEY, version);

            // Update VS Code config
            vscode.workspace.getConfiguration('neuroshell').update('executablePath', exePath, vscode.ConfigurationTarget.Global);

            // Re-inject terminal profile with new path
            injectNeuroShellProfile();

            // Clean up old files
            cleanupOldFiles(installDir);

            vscode.window.showInformationMessage(
                `NeuroShell updated to ${version}! Restart your terminal to use the new version.`,
                'Restart Terminal'
            ).then(choice => {
                if (choice === 'Restart Terminal') {
                    // Close all NeuroShell terminals and open a fresh one
                    vscode.window.terminals.forEach(t => {
                        if (t.name === 'NeuroShell') { t.dispose(); }
                    });
                    setTimeout(() => {
                        vscode.window.createTerminal({ name: 'NeuroShell' });
                    }, 500);
                }
            });

        } catch (err: any) {
            // Cleanup temp file on failure
            try { fs.unlinkSync(tempPath); } catch (_) {}
            vscode.window.showErrorMessage(`Update failed: ${err.message}`);
        }
    });
}

/**
 * Remove leftover .old and .update files from previous updates.
 */
function cleanupOldFiles(installDir: string) {
    try {
        const files = fs.readdirSync(installDir);
        for (const file of files) {
            if (file.endsWith('.old') || file.endsWith('.update')) {
                try {
                    fs.unlinkSync(path.join(installDir, file));
                } catch (_) {}
            }
        }
    } catch (_) {}
}


// ═══════════════════════════════════════════════════════════
// Install Engine (first-time)
// ═══════════════════════════════════════════════════════════

async function checkAndInstallEngine(context: vscode.ExtensionContext): Promise<void> {
    const isWindows = process.platform === 'win32';
    if (!isWindows) {
        return;
    }

    // PRIORITY 1: Python fallback (instant, no validation needed)
    const fallback = findPythonFallback();
    if (fallback) {
        // Dev mode — neuroshell_cli.py found in workspace, skip everything
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

    // Check if executable is custom set and exists
    if (configPath && configPath !== 'NeuroShell' && configPath !== 'NeuroShell-CLI' && fs.existsSync(configPath)) {
        if (!configPath.toLowerCase().endsWith('neuroshell.exe')) {
            return;
        }
    }

    // PRIORITY 2: Check standard installation paths (file existence only, no slow validation)
    const foundPath = findNeuroShellCLI();
    if (foundPath) {
        vscode.workspace.getConfiguration('neuroshell').update('executablePath', foundPath, vscode.ConfigurationTarget.Global);
        return;
    }

    // Prompt user to install
    const selection = await vscode.window.showInformationMessage(
        'NeuroShell engine not found on this system. Would you like to automatically download and install it?',
        'Install Now', 'Later'
    );

    if (selection === 'Install Now') {
        await downloadAndInstallLatest(context);
    }
}

/**
 * Download and install the LATEST version from GitHub (first-time install).
 */
async function downloadAndInstallLatest(context: vscode.ExtensionContext) {
    return vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: "Installing NeuroShell Engine",
        cancellable: false
    }, async (progress) => {
        const isWindows = process.platform === 'win32';
        if (!isWindows) {
            vscode.window.showInformationMessage('On Linux/macOS, please run: curl -sSL https://raw.githubusercontent.com/abneeshsingh21/neuroshell/main/scripts/install.sh | bash');
            return;
        }

        progress.report({ message: 'Fetching latest version...' });

        let downloadUrl: string;
        let version: string;

        try {
            const release = await fetchLatestRelease();
            version = release.tag_name;
            const exeAsset = release.assets.find(a => a.name.toLowerCase().endsWith('.exe'));
            if (!exeAsset) {
                throw new Error('No exe found in latest release');
            }
            downloadUrl = exeAsset.browser_download_url;
        } catch (e) {
            // Fallback to hardcoded URL if API fails
            downloadUrl = `https://github.com/${INSTALLER_REPO}/releases/download/v5.1.0/NeuroShell-CLI.exe`;
            version = 'v5.1.0';
        }

        progress.report({ message: `Downloading NeuroShell ${version} (~500MB)...` });

        const installDir = getInstallDir();
        const exePath = path.join(installDir, 'NeuroShell-CLI.exe');

        await downloadFile(downloadUrl, exePath, progress);

        // Save installed version
        context.globalState.update(VERSION_STATE_KEY, version);

        vscode.workspace.getConfiguration('neuroshell').update('executablePath', exePath, vscode.ConfigurationTarget.Global);
        vscode.window.showInformationMessage(`NeuroShell ${version} installed! Restart the terminal to use it.`);
        injectNeuroShellProfile();
    });
}


// ═══════════════════════════════════════════════════════════
// Download Helper
// ═══════════════════════════════════════════════════════════

function downloadFile(url: string, destPath: string, progress: vscode.Progress<{ message?: string }>): Promise<void> {
    return new Promise<void>((resolve, reject) => {
        const file = fs.createWriteStream(destPath);
        const request = (reqUrl: string) => {
            https.get(reqUrl, (response) => {
                if (response.statusCode === 301 || response.statusCode === 302) {
                    request(response.headers.location!);
                    return;
                }

                if (response.statusCode !== 200) {
                    reject(new Error(`Download failed with status ${response.statusCode}`));
                    return;
                }

                const totalSize = parseInt(response.headers['content-length'] || '0', 10);
                let downloaded = 0;

                response.on('data', (chunk: Buffer) => {
                    downloaded += chunk.length;
                    if (totalSize > 0) {
                        const percent = ((downloaded / totalSize) * 100).toFixed(0);
                        const downloadedMB = (downloaded / (1024 * 1024)).toFixed(1);
                        const totalMB = (totalSize / (1024 * 1024)).toFixed(0);
                        progress.report({ message: `${downloadedMB}MB / ${totalMB}MB (${percent}%)` });
                    }
                });

                response.pipe(file);
                file.on('finish', () => {
                    file.close();
                    progress.report({ message: 'Download complete! Configuring...' });
                    resolve();
                });
            }).on('error', (err) => {
                fs.unlink(destPath, () => {});
                reject(err);
            });
        };
        request(url);
    });
}


// ═══════════════════════════════════════════════════════════
// Terminal Profile Injection
// ═══════════════════════════════════════════════════════════

function injectNeuroShellProfile() {
    const config = vscode.workspace.getConfiguration('terminal.integrated');

    // Determine terminal command and args
    let terminalPath: string;
    let terminalArgs: string[];

    const isWindows = process.platform === 'win32';

    // PRIORITY 1: Always prefer Python fallback when neuroshell_cli.py is in workspace
    // This is instant, reliable, and doesn't depend on exe installation
    const fallback = findPythonFallback();
    if (fallback) {
        terminalPath = fallback.pythonPath;
        terminalArgs = ['-u', fallback.mainPyPath];
    } else {
        // PRIORITY 2: Use the compiled CLI exe from settings or discovery
        let neuroPath = vscode.workspace.getConfiguration('neuroshell').get<string>('executablePath') || 'NeuroShell-CLI';

        // Auto-migrate from GUI exe to CLI exe
        if (neuroPath.toLowerCase().endsWith('neuroshell.exe')) {
            const cliPath = path.join(path.dirname(neuroPath), 'NeuroShell-CLI.exe');
            if (fs.existsSync(cliPath)) {
                neuroPath = cliPath;
            }
        }

        if (neuroPath !== 'NeuroShell-CLI' && neuroPath !== 'NeuroShell' && fs.existsSync(neuroPath)) {
            if (neuroPath.toLowerCase().endsWith('neuroshell.exe')) {
                // NEVER inject the GUI app into the terminal
                terminalPath = isWindows ? 'NeuroShell-CLI' : 'neuroshell';
                terminalArgs = [];
            } else {
                // Use compiled CLI exe or absolute script path
                terminalPath = neuroPath;
                terminalArgs = [];
            }
        } else {
            // Last resort: try NeuroShell-CLI from PATH on Windows, neuroshell on Unix
            terminalPath = isWindows ? 'NeuroShell-CLI' : 'neuroshell';
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
