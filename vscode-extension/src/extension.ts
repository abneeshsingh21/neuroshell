import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {
    console.log('NeuroShell VS Code Extension is now active.');

    // Automatically inject the profile if not configured
    injectNeuroShellProfile();

    let disposable = vscode.commands.registerCommand('neuroshell.injectDefaultTerminal', () => {
        injectNeuroShellProfile();
        vscode.window.showInformationMessage('NeuroShell has been set as your default integrated terminal.');
    });

    context.subscriptions.push(disposable);
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
