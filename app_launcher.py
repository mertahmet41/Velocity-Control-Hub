import os
import sys
import json
import urllib.request
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
                
                download_url = f"https://github.com/{REPO}/releases/latest"
                for asset in data.get("assets", []):
                    if asset.get("name", "").lower().endswith(".exe"):
                        download_url = asset.get("browser_download_url")
                        break
                
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
