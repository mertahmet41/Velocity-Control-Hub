# -*- coding: utf-8 -*-
"""
Velocity Control Hub - Desktop Launcher
Launches the polished web UI in a dedicated frameless app window.
"""
import os
import sys
import webview

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "index.html")
    
    window = webview.create_window(
        title="Velocity Control Hub",
        url=html_path,
        width=1280,
        height=820,
        min_size=(1080, 720),
        background_color="#0a0b0d",
        resizable=True
    )
    webview.start()

if __name__ == "__main__":
    main()
