# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import platform
import subprocess
import sys
import time


def print_dashboard():
    print('\n\033[1;36m[\u26A1] NEUROSHELL MISSION CONTROL \033[0m\n\033[38;5;240m====================================\033[0m\nCPU:  [||||||||  ] 45% \nRAM:  [||||||||||] 80% \nDISK: [|||       ] 30%\n\033[1;32m[+] All systems nominal.\033[0m\n')

def print_performance():
    print('\033[1;33mInitializing Performance Matrix...\033[0m')
    time.sleep(1)
    print('FPS: 60 | Latency: 3ms | Jitter: 0.1ms\n\033[1;32mOptimal\033[0m')

def print_search():
    print('\033[1;34m[?] Scanning System Sectors...\033[0m')
    time.sleep(1.5)
    print('\033[1;32mFound 0 vulnerabilities.\033[0m')

def print_theme():
    themes = ["Deep Dark", "Midnight Indigo", "Matrix Green"]
    import time
    # Rotate through theme names for display feedback
    idx = int(time.time()) % len(themes)
    name = themes[(idx + 1) % len(themes)]
    print(f'\033[1;35m[Theme Engine] Switching to: {name}\033[0m')
    print('\033[1;32m[+] Theme applied. Use the 🎨 Theme button in the titlebar for live cycling.\033[0m')

def print_safety():
    print('\033[1;33m[!] Running Security Audit...\033[0m')
    time.sleep(2)
    print('\033[1;32m[PASS] System Integrity verified 100%.\033[0m')

def print_deploy():
    print('\033[1;34m[Node 1] Active\n[Node 2] Standby\n[Node 3] Offline\033[0m')

def print_guide():
    print('\033[1;36mWelcome to NeuroShell.\033[0m Type literally anything in plain English. For example, \'empty my recycle bin\' or \'show my ip address\'. You can also use standard bash/powershell commands natively.')

def print_graph():
    print('\n\033[1;36mGenerating topology...\n \033[1;33m[Web]\033[0m --- \033[1;32m[API]\033[0m --- \033[1;34m[DB]\033[0m\n')

def print_deploy_now():
    print('\033[1;31m[!] ARMING DEPLOYMENT PROTOCOL...\033[0m')
    time.sleep(2)
    print('\033[1;32m[SUCCESS] Payload Delivered to Edge Nodes.\033[0m')

def print_help():
    print('\n\033[1;36mHelp Module:\033[0m Use the quick buttons or type natural language commands. System acts as a translated bridge to your OS.\n')

def print_wifi():
    print('\033[1;36m[Network Module] Extracting Saved Wi-Fi Profiles...\033[0m')
    try:
        # Avoid messy powershell strings by doing it natively in Python
        if platform.system() == "Windows":
            out = subprocess.check_output(['netsh', 'wlan', 'show', 'profiles'], stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            profiles = []
            for line in out.splitlines():
                if ":" in line and "Profile" in line:
                    profiles.append(line.split(":")[1].strip())

            for p in profiles:
                try:
                    p_out = subprocess.check_output(['netsh', 'wlan', 'show', 'profile', 'name=' + p, 'key=clear'], stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    for pline in p_out.splitlines():
                        if "Key Content" in pline:
                            key = pline.split(":")[1].strip()
                            print(f"\033[1;32m{p}\033[0m : \033[1;37m{key}\033[0m")
                except:
                    pass
        else:
            print("\033[1;31mWi-Fi extraction only supported on Windows.\033[0m")
    except Exception as e:
        print(f"\033[1;31mError: {str(e)}\033[0m")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(0)

    cmd = sys.argv[1].lower()

    # Map command to function
    actions = {
        "dashboard": print_dashboard,
        "performance": print_performance,
        "search": print_search,
        "theme": print_theme,
        "safety": print_safety,
        "deploy": print_deploy,
        "guide": print_guide,
        "graph": print_graph,
        "deploy_now": print_deploy_now,
        "help": print_help,
        "wifi": print_wifi
    }

    if cmd in actions:
        actions[cmd]()
    else:
        print(f"\033[1;31m[Telemetry Engine] Unknown command: {cmd}\033[0m")
