import os
import sys
import json
import urllib.request
import webbrowser
import shutil
import time
import webview

REPO = "mertahmet41/Velocity-Control-Hub"

def parse_version_tuple(ver_str):
    try:
        parts = [int(x) for x in str(ver_str).lstrip('v').split('.') if x.isdigit()]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])
    except Exception:
        return (0, 0, 0)

def is_newer_version(latest_tag, current_tag):
    l_tuple = parse_version_tuple(latest_tag)
    c_tuple = parse_version_tuple(current_tag)
    if l_tuple != (0, 0, 0) or c_tuple != (0, 0, 0):
        return l_tuple > c_tuple
    return latest_tag != current_tag and bool(latest_tag)

def extract_version_from_html(html_path):
    if not os.path.exists(html_path):
        return "0.0.0"
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        import re
        match = re.search(r'CURRENT_APP_VERSION\s*=\s*["\']v?([^"\']+)["\']', content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "0.0.0"

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

    def perform_silent_update(self, download_url):
        try:
            live_html = get_html_path()
            
            # Download updated index.html directly from GitHub repository main branch with cache-buster
            timestamp = int(time.time())
            html_url = f"https://raw.githubusercontent.com/{REPO}/main/index.html?t={timestamp}"
            headers = {"User-Agent": "VelocityControlHubApp"}
            req = urllib.request.Request(html_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                new_html = resp.read()
                with open(live_html, 'wb') as f:
                    f.write(new_html)

            # Also update local directory index.html if accessible
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                local_html = os.path.join(base_dir, 'index.html')
                if os.path.exists(local_html) and not getattr(sys, 'frozen', False):
                    with open(local_html, 'wb') as f:
                        f.write(new_html)
            except Exception:
                pass

            # Instant live refresh in UI
            time.sleep(0.3)
            if self._window:
                self._window.load_url(f'file:///{live_html.replace("\\", "/")}')
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

def get_html_path():
    app_data_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'VelocityControlHub', 'app')
    os.makedirs(app_data_dir, exist_ok=True)
    live_html = os.path.join(app_data_dir, 'index.html')
    
    bundle_dir = get_base_dir()
    
    # Ensure static media assets exist in the live app directory
    for asset in ['pro_wheel.png', 'wheel.png', 'OpenFFBoard_F411CE_V3_Profiles.hex']:
        src = os.path.join(bundle_dir, asset)
        dst = os.path.join(app_data_dir, asset)
        if os.path.exists(src) and (not os.path.exists(dst) or os.path.getsize(dst) == 0):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass

    bundled_html = os.path.join(bundle_dir, 'index.html')
    if not os.path.exists(live_html):
        if os.path.exists(bundled_html):
            shutil.copy2(bundled_html, live_html)
    elif os.path.exists(bundled_html):
        bundled_ver = extract_version_from_html(bundled_html)
        live_ver = extract_version_from_html(live_html)
        if is_newer_version(bundled_ver, live_ver):
            try:
                shutil.copy2(bundled_html, live_html)
            except Exception:
                pass

    return live_html if os.path.exists(live_html) else bundled_html

def main():
    live_html = get_html_path()
    
    api = HubApi()
    window = webview.create_window(
        title='Velocity Control Hub - Pro Force Feedback Ecosystem',
        url=f'file:///{live_html.replace("\\", "/")}',
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
