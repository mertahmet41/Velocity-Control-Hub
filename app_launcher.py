import os
import sys
import json
import urllib.request
import subprocess
import tempfile
import webbrowser
import webview

REPO = "mertahmet41/Velocity-Control-Hub"

def is_newer_version(latest_tag, current_tag):
    try:
        l_parts = [int(x) for x in latest_tag.lstrip('v').split('.')]
        c_parts = [int(x) for x in current_tag.lstrip('v').split('.')]
        return l_parts > c_parts
    except Exception:
        return latest_tag != current_tag and latest_tag != ""

class HubApi:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def check_update(self, current_version):
        url = f"https://api.github.com/repos/{REPO}/releases/latest"
        headers = {
            "User-Agent": "VelocityControlHubApp",
            "Accept": "application/vnd.github.v3+json"
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                latest_tag = data.get("tag_name", "")
                body = data.get("body", "")
                html_url = data.get("html_url", "")
                
                # Prioritize standalone executable for silent in-place update
                download_url = None
                for asset in data.get("assets", []):
                    name = asset.get("name", "").lower()
                    if name == "velocitycontrolhub.exe":
                        download_url = asset.get("browser_download_url")
                        break
                
                # Fallback to setup exe if standalone not found
                if not download_url:
                    for asset in data.get("assets", []):
                        if asset.get("name", "").lower().endswith(".exe"):
                            download_url = asset.get("browser_download_url")
                            break

                if not download_url:
                    download_url = html_url
                
                has_update = is_newer_version(latest_tag, current_version)
                return {
                    "success": True,
                    "has_update": has_update,
                    "latest_tag": latest_tag,
                    "current_version": current_version,
                    "body": body,
                    "download_url": download_url
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def perform_silent_update(self, download_url):
        try:
            current_exe = os.path.abspath(sys.executable)
            is_frozen = getattr(sys, 'frozen', False)
            temp_dir = tempfile.gettempdir()
            update_exe = os.path.join(temp_dir, "VelocityControlHub_update.exe")

            # 1. Download updated binary in background
            headers = {"User-Agent": "VelocityControlHubApp"}
            req = urllib.request.Request(download_url, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as resp, open(update_exe, 'wb') as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

            # 2. In-place silent replacement and seamless restart
            if is_frozen:
                bat_path = os.path.join(temp_dir, "velocity_silent_restart.bat")
                with open(bat_path, "w", encoding="utf-8") as bat:
                    bat.write(f'''@echo off
timeout /t 1 /nobreak > nul
:retry
copy /y "{update_exe}" "{current_exe}" > nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak > nul
    goto retry
)
start "" "{current_exe}"
del "{update_exe}" > nul 2>&1
del "%~f0" > nul 2>&1
''')
                DETACHED_PROCESS = 0x00000008
                CREATE_NO_WINDOW = 0x08000000
                subprocess.Popen(
                    ["cmd.exe", "/c", bat_path],
                    creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
                    close_fds=True
                )
            else:
                # Script mode: update index.html directly from github
                try:
                    raw_html_url = f"https://raw.githubusercontent.com/{REPO}/main/index.html"
                    req_html = urllib.request.Request(raw_html_url, headers=headers)
                    with urllib.request.urlopen(req_html, timeout=10) as r:
                        content = r.read()
                        with open(os.path.join(os.path.dirname(__file__), 'index.html'), 'wb') as f:
                            f.write(content)
                except Exception as ex:
                    print("Script update error:", ex)
                subprocess.Popen([sys.executable] + sys.argv)

            # Close current instance cleanly
            if self._window:
                self._window.destroy()
            sys.exit(0)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_external(self, url):
        webbrowser.open(url)
        return {"success": True}

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def main():
    base_dir = get_base_dir()
    index_file = os.path.join(base_dir, 'index.html')
    
    api = HubApi()
    window = webview.create_window(
        title='Velocity Control Hub - Pro Force Feedback Ecosystem',
        url=f'file:///{index_file.replace("\\", "/")}',
        width=1280,
        height=820,
        min_size=(1024, 700),
        background_color='#0b0d13',
        js_api=api
    )
    api.set_window(window)
    webview.start(gui='edgechromium', debug=False)

if __name__ == '__main__':
    main()
