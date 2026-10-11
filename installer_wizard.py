# -*- coding: utf-8 -*-
"""
Setup Wizard & Uninstaller for Velocity Control Hub
Installs the program into C:\\Program Files\\Velocity Control Hub or AppData,
Creates Desktop/Start Menu shortcuts, and registers with Windows Control Panel.
"""

import os
import sys
import shutil
import winreg
from ctypes import wintypes
import ctypes

APP_NAME = "Velocity Control Hub"
PUBLISHER = "Mert Ahmet (Sim Racing Systems)"
VERSION = "3.0.0"

def get_install_dir():
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return os.path.join(local_app_data, "Programs", APP_NAME)

def install():
    print("=" * 60)
    print(f" {APP_NAME} Kurulum Sihirbazı v{VERSION}")
    print("=" * 60)
    
    source_dir = os.path.dirname(os.path.abspath(__file__))
    source_exe = os.path.join(source_dir, "dist", "Velocity_Control_Hub.exe")
    
    if not os.path.exists(source_exe):
        source_exe = os.path.join(source_dir, "Velocity_Control_Hub.exe")
        
    target_dir = get_install_dir()
    os.makedirs(target_dir, exist_ok=True)
    target_exe = os.path.join(target_dir, "Velocity_Control_Hub.exe")
    
    print(f"[1/4] Dosyalar yükleniyor: {target_dir}")
    shutil.copy2(source_exe, target_exe)
    
    # Copy uninstaller script to target
    uninstaller_path = os.path.join(target_dir, "Uninstall.bat")
    with open(uninstaller_path, "w", encoding="utf-8") as f:
        f.write(f'@echo off\necho {APP_NAME} kaldiriliyor...\n')
        f.write(f'reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" /f >nul 2>&1\n')
        f.write(f'del "%USERPROFILE%\\Desktop\\{APP_NAME}.lnk" >nul 2>&1\n')
        f.write(f'del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\{APP_NAME}.lnk" >nul 2>&1\n')
        f.write(f'rmdir /s /q "{target_dir}" >nul 2>&1\n')
        f.write('echo Basariyla kaldirildi.\npause\n')

    # [2/4] Create Windows Shortcuts
    print("[2/4] Masaüstü ve Başlat Menüsü kısayolları oluşturuluyor...")
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    start_menu = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")
    
    # Use PowerShell COM object for shortcuts
    ps_cmd = f'''
    $WshShell = New-Object -comObject WScript.Shell
    $s1 = $WshShell.CreateShortcut("{desktop}\\{APP_NAME}.lnk")
    $s1.TargetPath = "{target_exe}"
    $s1.WorkingDirectory = "{target_dir}"
    $s1.Save()

    $s2 = $WshShell.CreateShortcut("{start_menu}\\{APP_NAME}.lnk")
    $s2.TargetPath = "{target_exe}"
    $s2.WorkingDirectory = "{target_dir}"
    $s2.Save()
    '''
    os.system(f'powershell -Command "{ps_cmd}"')

    # [3/4] Register in Windows Control Panel (Programs and Features / Add or Remove Programs)
    print("[3/4] Windows Denetim Masası Program Ekle/Kaldır sistemine kaydediliyor...")
    reg_key_path = f"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, target_dir)
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, target_exe)
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller_path}"')
            winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, 45000)
    except Exception as e:
        print("Kayıt defteri uyarısı:", e)

    print("[4/4] Kurulum başarıyla tamamlandı!")
    print("\n✅ Program artık bilgisayarınızda resmi bir Windows yazılımı olarak kuruldu.")
    print("✅ Denetim Masası / Program Ekle-Kaldır listesinde görünecektir.")

if __name__ == "__main__":
    install()
