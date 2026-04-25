# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
#!/usr/bin/env python3
"""
Create a Desktop shortcut for NeuroShell Desktop.
Run once: python create_shortcut.py
"""

import os
import sys


def create_shortcut():
    """Create a Windows desktop shortcut for NeuroShell."""
    try:
        import winreg
        # Use Windows Script Host COM for .lnk creation
        try:
            from win32com.client import Dispatch
            use_com = True
        except ImportError:
            use_com = False

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut_path = os.path.join(desktop, "NeuroShell.lnk")

        app_dir = os.path.dirname(os.path.abspath(__file__))
        bat_path = os.path.join(app_dir, "launch_neuroshell.bat")

        if use_com:
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.TargetPath = bat_path
            shortcut.WorkingDirectory = app_dir
            shortcut.Description = "NeuroShell — AI-Powered Terminal"
            shortcut.WindowStyle = 7  # Minimized (bat window hidden)

            icon_path = os.path.join(app_dir, "assets", "icon.ico")
            if os.path.exists(icon_path):
                shortcut.IconLocation = icon_path

            shortcut.save()
            print(f"✅ Desktop shortcut created: {shortcut_path}")
        else:
            # Fallback: create a .bat shortcut on desktop
            desktop_bat = os.path.join(desktop, "NeuroShell.bat")
            with open(desktop_bat, "w") as f:
                f.write(f'@echo off\ncd /d "{app_dir}"\ncall launch_neuroshell.bat\n')
            print(f"✅ Desktop launcher created: {desktop_bat}")
            print("   💡 For a proper shortcut icon, install pywin32: pip install pywin32")

    except Exception as e:
        # Ultimate fallback — just create a simple .bat on desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        app_dir = os.path.dirname(os.path.abspath(__file__))
        desktop_bat = os.path.join(desktop, "NeuroShell.bat")
        with open(desktop_bat, "w") as f:
            f.write(f'@echo off\ncd /d "{app_dir}"\ncall launch_neuroshell.bat\n')
        print(f"✅ Desktop launcher created: {desktop_bat}")


if __name__ == "__main__":
    create_shortcut()
