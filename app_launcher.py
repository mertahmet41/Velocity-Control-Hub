import os
import sys
import json
import urllib.request
import subprocess
import tempfile
import webbrowser
import webview

REPO = "mertahmet41/Velocity-Control-Hub"

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
                
                download_url = html_url
                for asset in data.get("assets", []):
                    if asset.get("name", "").lower().endswith(".exe"):
                        download_url = asset.get("browser_download_url")
                        break
                
                has_update = (latest_tag != "" and latest_tag != current_version)
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

    def download_and_install_update(self, download_url):
        try:
            temp_dir = tempfile.gettempdir()
            setup_path = os.path.join(temp_dir, "Velocity_Control_Hub_Setup.exe")
            
            headers = {"User-Agent": "VelocityControlHubApp"}
            req = urllib.request.Request(download_url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=120) as response, open(setup_path, 'wb') as out_file:
                chunk_size = 64 * 1024
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
            
            subprocess.Popen([setup_path], shell=True)
            
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
