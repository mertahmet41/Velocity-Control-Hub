import os
import sys
import re
import json
import glob
import urllib.request
import webbrowser
import shutil
import time
import subprocess
import threading
import hashlib

try:
    import webview
    WEBVIEW_OK = True
except Exception:
    WEBVIEW_OK = False

try:
    import serial
    import serial.tools.list_ports
    SERIAL_OK = True
except Exception:
    SERIAL_OK = False

try:
    import usb.core
    import usb.util
    PYUSB_OK = True
except Exception:
    PYUSB_OK = False

REPO = "mertahmet41/Velocity-Control-Hub"
FIRMWARE_PREFIX = "OpenFFBoard_F411CE_V3_Profiles"
STM32_DFU_VID = 0x0483
STM32_DFU_PID = 0xDF11


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_app_data_dir():
    base = os.environ.get('VELOCITY_APPDATA_DIR') or os.path.join(
        os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
        'VelocityControlHub'
    )
    os.makedirs(base, exist_ok=True)
    return base


def get_settings_file_path():
    return os.path.join(get_app_data_dir(), 'settings.json')


def load_version_config(base_dir=None):
    """Single source of truth for application and bundled firmware version."""
    search_dirs = [base_dir or get_base_dir(), os.path.dirname(os.path.abspath(__file__))]
    for d in search_dirs:
        if not d:
            continue
        vpath = os.path.join(d, 'version.json')
        if os.path.exists(vpath):
            try:
                with open(vpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                ver = str(data.get('version', '0.0.0')).lstrip('v')
                prefix = data.get('firmware_prefix', FIRMWARE_PREFIX)
                return {
                    "version": ver,
                    "tag": f"v{ver}",
                    "firmware_prefix": prefix,
                    "firmware_hex": data.get('firmware_hex', f"{prefix}_v{ver}.hex")
                }
            except Exception:
                pass
    return {
        "version": "3.16.0",
        "tag": "v3.16.0",
        "firmware_prefix": FIRMWARE_PREFIX,
        "firmware_hex": f"{FIRMWARE_PREFIX}_v3.16.0.hex"
    }


def parse_version_tuple(ver_str):
    try:
        if not ver_str:
            return (0, 0, 0)
        cleaned = str(ver_str).strip().lstrip('vV')
        m = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', cleaned)
        if not m:
            return (0, 0, 0)
        major = int(m.group(1))
        minor = int(m.group(2))
        patch = int(m.group(3)) if m.group(3) is not None else 0
        return (major, minor, patch)
    except Exception:
        return (0, 0, 0)


def format_version_str(ver_str):
    t = parse_version_tuple(ver_str)
    if t == (0, 0, 0):
        return ""
    return f"{t[0]}.{t[1]}.{t[2]}"


def is_newer_version(candidate_ver, current_ver):
    l_tuple = parse_version_tuple(candidate_ver)
    c_tuple = parse_version_tuple(current_ver)
    if l_tuple != (0, 0, 0) and c_tuple != (0, 0, 0):
        return l_tuple > c_tuple
    if l_tuple != (0, 0, 0) and c_tuple == (0, 0, 0):
        return True
    return False


def parse_version_from_hex_filename(hex_path_or_name):
    """Extract semantic version X.Y.Z from a versioned .hex filename."""
    if not hex_path_or_name:
        return ""
    basename = os.path.basename(str(hex_path_or_name))
    # Match patterns like OpenFFBoard_F411CE_V3_Profiles_v3.14.0.hex or FFBoard_v1.2.3.hex
    m = re.search(r'[_\-]v?(\d+\.\d+\.\d+)\.hex$', basename, re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.search(r'v(\d+\.\d+\.\d+)', basename, re.IGNORECASE)
    if m2:
        return m2.group(1)
    return ""


def validate_intel_hex(hex_path):
    """Validate an Intel HEX file for STM32F4 flash programming."""
    if not hex_path or not os.path.exists(hex_path):
        return {
            "valid": False,
            "error": "Firmware (.hex) dosyasi bulunamadi."
        }
    try:
        file_size = os.path.getsize(hex_path)
        if file_size < 64:
            return {
                "valid": False,
                "error": "Firmware (.hex) dosyasi bos veya cok kucuk."
            }
        with open(hex_path, 'r', encoding='utf-8', errors='strict') as f:
            lines = f.readlines()
    except Exception as e:
        return {
            "valid": False,
            "error": f"Firmware (.hex) dosyasi okunamadi: {e}"
        }

    record_count = 0
    data_bytes = 0
    has_eof = False
    upper_addr = 0
    has_stm32_flash_addr = False

    for idx, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if not line.startswith(':'):
            return {
                "valid": False,
                "error": f"Bozuk HEX dosyasi (Satir {idx}: ':' ile baslamiyor)."
            }
        hex_digits = line[1:]
        if len(hex_digits) < 10 or (len(hex_digits) % 2) != 0:
            return {
                "valid": False,
                "error": f"Bozuk HEX dosyasi (Satir {idx}: gecersiz kayıt uzunlugu)."
            }
        try:
            raw_bytes = bytes.fromhex(hex_digits)
        except ValueError:
            return {
                "valid": False,
                "error": f"Bozuk HEX dosyasi (Satir {idx}: gecersiz onaltilik karakter)."
            }

        byte_count = raw_bytes[0]
        if len(raw_bytes) != byte_count + 5:
            return {
                "valid": False,
                "error": f"Bozuk HEX dosyasi (Satir {idx}: veri uzunlugu uyusmuyor)."
            }

        # Verify Intel HEX two's complement checksum
        if (sum(raw_bytes) & 0xFF) != 0:
            return {
                "valid": False,
                "error": f"Bozuk HEX dosyasi (Satir {idx}: checksum/saglama toplami hatasi)."
            }

        rec_type = raw_bytes[3]
        addr16 = (raw_bytes[1] << 8) | raw_bytes[2]
        record_count += 1

        if rec_type == 0x00:  # Data
            data_bytes += byte_count
            full_addr = (upper_addr << 16) | addr16
            if 0x08000000 <= full_addr <= 0x08080000:
                has_stm32_flash_addr = True
        elif rec_type == 0x01:  # EOF
            has_eof = True
            break
        elif rec_type == 0x04:  # Extended Linear Address
            if byte_count == 2:
                upper_addr = (raw_bytes[4] << 8) | raw_bytes[5]

    if not has_eof:
        return {
            "valid": False,
            "error": "Bozuk HEX dosyasi: Dosya sonu (EOF) kaydi eksik."
        }
    if data_bytes == 0 or not has_stm32_flash_addr:
        return {
            "valid": False,
            "error": "Gecersiz HEX dosyasi: STM32 Flash (0x08000000) veri blogu bulunamadi."
        }

    return {
        "valid": True,
        "record_count": record_count,
        "data_bytes": data_bytes,
        "file_size": file_size
    }


def intel_hex_to_segments(hex_path):
    """Parse Intel HEX into contiguous [(start_addr, bytearray), ...] segments."""
    check = validate_intel_hex(hex_path)
    if not check.get("valid"):
        raise ValueError(check.get("error", "Gecersiz HEX dosyasi"))

    upper_addr = 0
    mem = {}
    with open(hex_path, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            raw = bytes.fromhex(line[1:])
            cnt = raw[0]
            addr16 = (raw[1] << 8) | raw[2]
            rtype = raw[3]
            data = raw[4:4 + cnt]
            if rtype == 0x00:
                base = (upper_addr << 16) | addr16
                for i, b in enumerate(data):
                    mem[base + i] = b
            elif rtype == 0x01:
                break
            elif rtype == 0x04 and cnt == 2:
                upper_addr = (data[0] << 8) | data[1]

    if not mem:
        return []
    addrs = sorted(mem.keys())
    segments = []
    seg_start = addrs[0]
    seg_buf = bytearray([mem[seg_start]])
    prev = seg_start
    for a in addrs[1:]:
        if a == prev + 1:
            seg_buf.append(mem[a])
        else:
            segments.append((seg_start, seg_buf))
            seg_start = a
            seg_buf = bytearray([mem[a]])
        prev = a
    segments.append((seg_start, seg_buf))
    return segments


def extract_version_from_html(html_path):
    if not os.path.exists(html_path):
        return "0.0.0"
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        match = re.search(r'CURRENT_APP_VERSION\s*=\s*["\']v?([^"\']+)["\']', content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "0.0.0"


class HubApi:
    KNOWN_IDS = [(0x1209, 0xFFB0), (0x046D, 0xC24F), (0x346E, 0x0002), (0x0483, None)]

    def __init__(self, search_dirs=None):
        self._window = None
        self._ser = None
        self._port_name = None
        self._rx = bytearray()
        self._alive = False
        self._lock = threading.Lock()
        self._search_dirs = search_dirs
        self._fw_status = {
            "running": False,
            "step": "idle",
            "percent": 0,
            "message": "Hazir",
            "error": None,
            "result": None
        }
        # Hooks for automated testing / simulation when physical hardware is absent
        self._sim_hooks = None

    def set_window(self, window):
        self._window = window

    def set_simulation_hooks(self, hooks):
        """Used by unit/integration test suite to simulate serial & DFU hardware transitions."""
        self._sim_hooks = hooks

    # ------------------------------------------------------------------
    # Persistent Settings Management (settings.json)
    # ------------------------------------------------------------------
    def _default_settings(self):
        return {
            "developer_mode": False,
            "encoder_cpr": 2400,
            "drive_profile": "gt3",
            "auto_connect": True,
            "auto_reconnect": True,
            "auto_update": True,
            "accent_color": "#00b4d8",
            "nrf24_enabled": True,
            "nrf24_channel": 76
        }

    def get_settings(self):
        defaults = self._default_settings()
        spath = get_settings_file_path()
        if os.path.exists(spath):
            try:
                with open(spath, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    defaults.update(loaded)
            except Exception:
                pass
        return {"success": True, "settings": defaults, "path": spath}

    def save_settings(self, partial_settings):
        try:
            cur = self.get_settings().get("settings", self._default_settings())
            if isinstance(partial_settings, str):
                partial_settings = json.loads(partial_settings)
            if isinstance(partial_settings, dict):
                cur.update(partial_settings)
            # Never allow encoder_cpr to be lost or zeroed
            if not isinstance(cur.get("encoder_cpr"), int) or cur.get("encoder_cpr", 0) <= 0:
                cur["encoder_cpr"] = 2400
            spath = get_settings_file_path()
            with open(spath, 'w', encoding='utf-8') as f:
                json.dump(cur, f, indent=2, ensure_ascii=False)
            return {"success": True, "settings": cur, "path": spath}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Version & Firmware File Discovery (Single Source of Truth)
    # ------------------------------------------------------------------
    def _candidate_firmware_dirs(self):
        if self._search_dirs is not None:
            return [d for d in self._search_dirs if d and os.path.isdir(d)]
        base = get_base_dir()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.join(get_app_data_dir(), 'app')
        dirs = [
            os.path.join(script_dir, 'Firmware'),
            script_dir,
            os.path.join(base, 'Firmware'),
            base,
            os.path.join(app_dir, 'Firmware'),
            app_dir,
        ]
        seen = []
        for d in dirs:
            norm = os.path.normcase(os.path.abspath(d))
            if norm not in seen and os.path.isdir(d):
                seen.append(norm)
        return [d for d in dirs if os.path.isdir(d)]

    def resolve_firmware_hex(self, custom_hex_path=None):
        """
        Locate the newest versioned firmware .hex file and parse its version
        directly from the filename.
        """
        vcfg = load_version_config()
        if custom_hex_path:
            ver = parse_version_from_hex_filename(custom_hex_path)
            validation = validate_intel_hex(custom_hex_path)
            return {
                "success": validation.get("valid", False) and bool(ver),
                "hex_path": custom_hex_path,
                "hex_filename": os.path.basename(custom_hex_path),
                "hex_version": ver,
                "validation": validation,
                "app_version": vcfg["version"],
                "error": validation.get("error") if not validation.get("valid") else (
                    "Hex dosya adinda surum numarasi bulunamadi (orn: OpenFFBoard_F411CE_V3_Profiles_v3.14.0.hex)." if not ver else None
                )
            }

        candidates = []
        for d in self._candidate_firmware_dirs():
            for path in glob.glob(os.path.join(d, "*.hex")):
                ver = parse_version_from_hex_filename(path)
                if ver:
                    candidates.append((parse_version_tuple(ver), ver, path))

        if candidates:
            # Sort by highest version tuple
            candidates.sort(key=lambda item: item[0], reverse=True)
            _, best_ver, best_path = candidates[0]
            validation = validate_intel_hex(best_path)
            return {
                "success": validation.get("valid", False),
                "hex_path": best_path,
                "hex_filename": os.path.basename(best_path),
                "hex_version": best_ver,
                "validation": validation,
                "app_version": vcfg["version"],
                "error": validation.get("error") if not validation.get("valid") else None
            }

        return {
            "success": False,
            "hex_path": "",
            "hex_filename": "",
            "hex_version": "",
            "validation": {"valid": False, "error": "Surumlu firmware (.hex) dosyasi bulunamadi."},
            "app_version": vcfg["version"],
            "error": "Surumlu firmware (.hex) dosyasi bulunamadi."
        }

    def get_version_info(self):
        vcfg = load_version_config()
        fw = self.resolve_firmware_hex()
        return {
            "success": True,
            "app_version": vcfg["version"],
            "app_tag": vcfg["tag"],
            "firmware_hex": fw.get("hex_filename") or vcfg["firmware_hex"],
            "firmware_version": fw.get("hex_version") or vcfg["version"],
            "firmware_path": fw.get("hex_path", ""),
            "firmware_valid": fw.get("validation", {}).get("valid", False)
        }

    def get_firmware_path(self):
        info = self.resolve_firmware_hex()
        return info.get("hex_path", "")

    # ------------------------------------------------------------------
    # Native Serial Bridge & Direct Device Query Helpers
    # ------------------------------------------------------------------
    def _is_known(self, vid, pid):
        for v, p in self.KNOWN_IDS:
            if vid == v and (p is None or pid == p):
                return True
        return False

    def list_devices(self):
        """Return COM ports; only OpenFFBoard / G29 / Moza / STM32 are flagged as match."""
        if self._sim_hooks and "list_devices" in self._sim_hooks:
            return self._sim_hooks["list_devices"]()
        if not SERIAL_OK:
            return {"success": False, "error": "pyserial yuklu degil", "devices": []}
        out = []
        try:
            for p in serial.tools.list_ports.comports():
                out.append({
                    "port": p.device,
                    "vid": p.vid or 0,
                    "pid": p.pid or 0,
                    "desc": p.description or "",
                    "match": bool(p.vid) and self._is_known(p.vid, p.pid),
                })
        except Exception as e:
            return {"success": False, "error": str(e), "devices": []}
        return {"success": True, "devices": out}

    def serial_open(self, port_name):
        if self._sim_hooks and "serial_open" in self._sim_hooks:
            return self._sim_hooks["serial_open"](port_name)
        self.serial_close()
        try:
            ser = serial.Serial(port_name, 115200, timeout=0.05, write_timeout=1)
            try:
                ser.dtr = True
                ser.rts = True
            except Exception:
                pass
            self._ser = ser
            self._port_name = port_name
            self._rx = bytearray()
            self._alive = True
            t = threading.Thread(target=self._reader, args=(ser,), daemon=True)
            t.start()
            return {"success": True, "port": port_name}
        except Exception as e:
            self._ser = None
            self._port_name = None
            return {"success": False, "error": str(e)}

    def _reader(self, ser):
        while self._alive and self._ser is ser:
            try:
                data = ser.read(256)
                if data:
                    with self._lock:
                        self._rx.extend(data)
                        if len(self._rx) > 65536:
                            del self._rx[:len(self._rx) - 65536]
            except Exception:
                self._alive = False
                break

    def serial_read(self):
        if self._sim_hooks and "serial_read" in self._sim_hooks:
            return self._sim_hooks["serial_read"]()
        if self._ser is None or not self._alive:
            return {"success": False, "connected": False, "data": ""}
        with self._lock:
            data = bytes(self._rx)
            self._rx.clear()
        return {"success": True, "connected": True, "data": data.decode("utf-8", errors="ignore")}

    def serial_write(self, text):
        if self._sim_hooks and "serial_write" in self._sim_hooks:
            return self._sim_hooks["serial_write"](text)
        if self._ser is None or not self._alive:
            return {"success": False, "error": "bagli degil"}
        try:
            self._ser.write(str(text).encode("utf-8"))
            return {"success": True}
        except Exception as e:
            self._alive = False
            return {"success": False, "error": str(e)}

    def serial_close(self):
        if self._sim_hooks and "serial_close" in self._sim_hooks:
            return self._sim_hooks["serial_close"]()
        self._alive = False
        ser = self._ser
        self._ser = None
        self._port_name = None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        return {"success": True}

    def _query_serial_Sync(self, cmd, timeout_s=1.5):
        """Send a command over the active serial connection and wait for [cmd|val] response."""
        if self._sim_hooks and "query_cmd" in self._sim_hooks:
            return self._sim_hooks["query_cmd"](cmd, timeout_s)

        was_open = (self._ser is not None and self._alive)
        if not was_open:
            devs = self.list_devices().get("devices", [])
            matched = [d for d in devs if d.get("match")]
            if not matched:
                return None
            opened = self.serial_open(matched[0]["port"])
            if not opened.get("success"):
                return None

        key = cmd.strip().replace('?', '').replace('=', '').lower()
        with self._lock:
            self._rx.clear()

        w = self.serial_write(cmd.strip() + "\n")
        if not w.get("success"):
            return None

        t0 = time.time()
        acc = ""
        while time.time() - t0 < timeout_s:
            r = self.serial_read()
            if not r.get("connected"):
                return None
            if r.get("data"):
                acc += r["data"]
                for raw_line in acc.splitlines():
                    line = raw_line.strip()
                    m = re.match(r'^\[([^|\]]+)\|([^\]]*)\]$', line)
                    if m:
                        resp_key = m.group(1).split('?')[0].split('=')[0].strip().lower()
                        if resp_key == key or resp_key.endswith("." + key) or key.endswith("." + resp_key):
                            return m.group(2).strip()
            time.sleep(0.03)
        return None

    def read_device_firmware_version(self):
        """Read actual firmware version from STM32 over USB serial (no fake/hardcoded fallback)."""
        sw = self._query_serial_Sync("sys.swver?", timeout_s=1.5)
        hw = self._query_serial_Sync("sys.hwtype?", timeout_s=1.0)
        if not sw:
            return {
                "success": False,
                "connected": False,
                "device_version": "",
                "hw_type": "",
                "error": "STM32 cihazi bagli degil veya yanit vermiyor."
            }
        clean_ver = format_version_str(sw) or sw.strip()
        return {
            "success": True,
            "connected": True,
            "device_version": clean_ver,
            "hw_type": hw or "STM32F411CE",
            "error": None
        }

    def check_device_firmware_status(self, custom_hex_path=None):
        """
        Compare live STM32 firmware version with the version parsed from the target .hex filename.
        """
        hex_info = self.resolve_firmware_hex(custom_hex_path)
        dev_info = self.read_device_firmware_version()

        hex_ver = hex_info.get("hex_version", "")
        hex_valid = hex_info.get("validation", {}).get("valid", False)
        dev_ver = dev_info.get("device_version", "")
        connected = dev_info.get("connected", False)

        if not hex_valid or not hex_ver:
            return {
                "success": False,
                "connected": connected,
                "device_version": dev_ver,
                "hex_version": hex_ver,
                "hex_filename": hex_info.get("hex_filename", ""),
                "has_update": False,
                "same_version": False,
                "error": hex_info.get("error") or "Gecerli bir firmware (.hex) dosyasi bulunamadi."
            }

        if not connected:
            return {
                "success": True,
                "connected": False,
                "device_version": "",
                "hex_version": hex_ver,
                "hex_filename": hex_info.get("hex_filename", ""),
                "has_update": False,
                "same_version": False,
                "status_text": "Cihaz bagli degil. Guncelleme icin direksiyonu USB ile baglayin.",
                "error": None
            }

        has_update = is_newer_version(hex_ver, dev_ver)
        same_version = (parse_version_tuple(hex_ver) == parse_version_tuple(dev_ver)) and (parse_version_tuple(hex_ver) != (0, 0, 0))

        if has_update:
            status_text = f"Yeni firmware surumu mevcut: v{hex_ver} (Cihazdaki: v{dev_ver})"
        elif same_version:
            status_text = f"Cihaziniz guncel (v{dev_ver})"
        else:
            status_text = f"Cihaz surumu: v{dev_ver} | Paket surumu: v{hex_ver}"

        return {
            "success": True,
            "connected": True,
            "device_version": dev_ver,
            "hw_type": dev_info.get("hw_type", ""),
            "hex_version": hex_ver,
            "hex_filename": hex_info.get("hex_filename", ""),
            "hex_path": hex_info.get("hex_path", ""),
            "has_update": has_update,
            "same_version": same_version,
            "status_text": status_text,
            "error": None
        }

    # ------------------------------------------------------------------
    # Automatic DFU Bootloader Detection & Programming
    # ------------------------------------------------------------------
    def _find_stm32_programmer_cli(self):
        candidates = [
            r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe",
            r"C:\Program Files (x86)\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        in_path = shutil.which("STM32_Programmer_CLI")
        return in_path or ""

    def _find_dfu_util(self):
        base = get_base_dir()
        local_dfu = os.path.join(base, "dfu-util.exe")
        if os.path.exists(local_dfu):
            return local_dfu
        return shutil.which("dfu-util") or ""

    def is_dfu_device_present(self):
        """Check whether an STM32 in USB DFU mode (0483:DF11) is connected."""
        if self._sim_hooks and "is_dfu_device_present" in self._sim_hooks:
            return bool(self._sim_hooks["is_dfu_device_present"]())

        # 1. Check via pyusb if libusb backend is available
        if PYUSB_OK:
            try:
                dev = usb.core.find(idVendor=STM32_DFU_VID, idProduct=STM32_DFU_PID)
                if dev is not None:
                    return True
            except Exception:
                pass

        # 2. Check via STM32_Programmer_CLI -l usb
        cli = self._find_stm32_programmer_cli()
        if cli:
            try:
                proc = subprocess.run(
                    [cli, "-l", "usb"],
                    capture_output=True,
                    text=True,
                    timeout=4,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                out = (proc.stdout or "") + (proc.stderr or "")
                if "DFU in FS Mode" in out or "USB1" in out or "0xDF11" in out or "Device Index" in out:
                    if "No STM32 device in DFU mode connected" not in out:
                        return True
            except Exception:
                pass

        # 3. Check via Windows PnP USB VID_0483&PID_DF11
        if sys.platform == "win32":
            try:
                proc = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_0483&PID_DF11' } | Select-Object -ExpandProperty InstanceId"],
                    capture_output=True,
                    text=True,
                    timeout=4,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                if "VID_0483&PID_DF11" in (proc.stdout or "").upper():
                    return True
            except Exception:
                pass

        return False

    def enter_dfu_mode_automatically(self, wait_timeout_s=8.0):
        """
        Switch the connected STM32 into ROM DFU bootloader mode via software serial command
        without requiring any physical BOOT0 jumper or button press.
        """
        if self._sim_hooks and "enter_dfu" in self._sim_hooks:
            return self._sim_hooks["enter_dfu"](wait_timeout_s)

        if self.is_dfu_device_present():
            return {"success": True, "already_in_dfu": True}

        was_open = (self._ser is not None and self._alive)
        if not was_open:
            devs = self.list_devices().get("devices", [])
            matched = [d for d in devs if d.get("match")]
            if not matched:
                return {
                    "success": False,
                    "code": "DEVICE_NOT_CONNECTED",
                    "error": "STM32 cihazi bulunamadi. Otomatik DFU gecisi icin cihazin USB ile bagli olmasi gerekir."
                }
            opened = self.serial_open(matched[0]["port"])
            if not opened.get("success"):
                return {
                    "success": False,
                    "code": "SERIAL_OPEN_FAILED",
                    "error": f"STM32 seri portu acilamadi: {opened.get('error')}"
                }

        # Send both sys.dfu? (compatible with v1.17.1 / v3.13.0) and sys.dfu=1 (compatible with v3.14.0+)
        try:
            self.serial_write("sys.dfu?\nsys.dfu=1\n")
            time.sleep(0.15)
        except Exception:
            pass
        finally:
            self.serial_close()

        # Poll for STM32 DFU USB enumeration (VID 0x0483, PID 0xDF11)
        t0 = time.time()
        while time.time() - t0 < wait_timeout_s:
            if self.is_dfu_device_present():
                return {"success": True, "already_in_dfu": False}
            time.sleep(0.35)

        return {
            "success": False,
            "code": "DFU_TRANSITION_FAILED",
            "error": (
                "Cihaz otomatik olarak DFU (guncelleme) moduna gecirilemedi. "
                "USB baglantisinin kopmadigindan ve STM32 Bootloader surucusunun yuklu oldugundan emin olun."
            )
        }

    def _flash_with_stm32cube_cli(self, cli_path, hex_path, progress_cb=None):
        """Program and verify STM32 Flash using official STM32_Programmer_CLI and auto-reset (-rst)."""
        cmd = [cli_path, "-c", "port=USB1", "-w", hex_path, "-v", "-rst"]
        try:
            if progress_cb:
                progress_cb(45, "STM32 Flash bellegine yeni firmware yaziliyor...")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            if proc.returncode == 0 and ("File download complete" in out or "Verify successfully" in out or "Download verified successfully" in out):
                if progress_cb:
                    progress_cb(80, "Firmware yazildi ve dogrulandi. Cihaz yeniden baslatiliyor...")
                return {"success": True, "output": out}
            return {
                "success": False,
                "code": "FLASH_FAILED",
                "error": "Firmware yukleme sirasinda hata olustu. USB baglantisini kontrol edin.",
                "details": out[-600:]
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "code": "FLASH_TIMEOUT",
                "error": "Firmware yukleme islemi zaman asimina ugradi."
            }
        except Exception as e:
            return {
                "success": False,
                "code": "FLASH_EXCEPTION",
                "error": f"Firmware yukleyici calistirilamadi: {e}"
            }

    def _flash_with_dfu_util(self, dfu_util_path, hex_path, progress_cb=None):
        """Fallback DFU programmer using dfu-util with contiguous binary image."""
        segments = intel_hex_to_segments(hex_path)
        if not segments:
            return {"success": False, "code": "EMPTY_HEX", "error": "HEX dosyasinda veri bulunamadi."}
        min_addr = segments[0][0]
        max_addr = max(addr + len(buf) for addr, buf in segments)
        image = bytearray([0xFF] * (max_addr - min_addr))
        for addr, buf in segments:
            offset = addr - min_addr
            image[offset:offset + len(buf)] = buf

        tmp_bin = os.path.join(get_app_data_dir(), "temp_fw_dfu.bin")
        try:
            with open(tmp_bin, "wb") as f:
                f.write(image)
            if progress_cb:
                progress_cb(45, "DFU uzerinden firmware yaziliyor...")
            cmd = [
                dfu_util_path,
                "-d", "0483:df11",
                "-a", "0",
                "-s", f"0x{min_addr:08X}:leave",
                "-D", tmp_bin
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            if proc.returncode == 0 or "File downloaded successfully" in out:
                return {"success": True, "output": out}
            return {
                "success": False,
                "code": "FLASH_FAILED",
                "error": "DFU uzerinden firmware yuklenemedi.",
                "details": out[-600:]
            }
        finally:
            if os.path.exists(tmp_bin):
                try:
                    os.remove(tmp_bin)
                except Exception:
                    pass

    def _update_fw_status(self, running, step, percent, message, error=None, result=None):
        self._fw_status = {
            "running": running,
            "step": step,
            "percent": int(percent),
            "message": message,
            "error": error,
            "result": result
        }

    def get_firmware_update_progress(self):
        return dict(self._fw_status)

    def perform_device_firmware_update(self, custom_hex_path=None, force=False):
        """
        Full end-to-end single-click STM32 firmware update flow:
        1. Validate target .hex file and parse target version from filename.
        2. Read current firmware version from STM32 over serial & compare.
        3. Automatically switch STM32 into DFU mode via software command (no jumper/button).
        4. Program .hex into STM32 Flash, verify bytes, and reset MCU back to normal mode.
        5. Reconnect to STM32 serial port, read sys.swver?, and verify it matches target version.
        """
        self._update_fw_status(True, "validate", 5, "Firmware paketi (.hex) dogrulaniyor...")

        # Step 1: Resolve & validate .hex file
        hex_info = self.resolve_firmware_hex(custom_hex_path)
        validation = hex_info.get("validation", {})
        if not validation.get("valid") or not hex_info.get("hex_version"):
            err_msg = hex_info.get("error") or validation.get("error") or "Gecersiz firmware (.hex) dosyasi."
            res = {
                "success": False,
                "code": "INVALID_HEX",
                "error": err_msg
            }
            self._update_fw_status(False, "error", 0, err_msg, error=err_msg, result=res)
            return res

        target_ver = hex_info["hex_version"]
        hex_path = hex_info["hex_path"]
        hex_filename = hex_info["hex_filename"]

        # Step 2: Read current device version (unless already in DFU mode)
        self._update_fw_status(True, "read_version", 15, "Cihazdaki mevcut firmware surumu okunuyor...")
        dev_ver_info = self.read_device_firmware_version()
        old_ver = dev_ver_info.get("device_version", "")

        if not dev_ver_info.get("connected"):
            # Check if device is already waiting in DFU mode
            if not self.is_dfu_device_present():
                err_msg = "STM32 cihazi bagli degil. Lutfen USB kablosunun takili oldugundan emin olun."
                res = {
                    "success": False,
                    "code": "DEVICE_DISCONNECTED",
                    "error": err_msg
                }
                self._update_fw_status(False, "error", 0, err_msg, error=err_msg, result=res)
                return res
        else:
            # Compare versions
            if not force and parse_version_tuple(old_ver) == parse_version_tuple(target_ver) and parse_version_tuple(target_ver) != (0, 0, 0):
                err_msg = f"Cihazda zaten ayni firmware surumu (v{target_ver}) yuklu."
                res = {
                    "success": False,
                    "code": "SAME_VERSION",
                    "old_version": old_ver,
                    "target_version": target_ver,
                    "hex_filename": hex_filename,
                    "error": err_msg
                }
                self._update_fw_status(False, "same_version", 100, err_msg, error=err_msg, result=res)
                return res

        # Step 3: Automatic transition to DFU mode
        self._update_fw_status(True, "enter_dfu", 30, "Cihaz otomatik olarak guncelleme (DFU) moduna geciriliyor...")
        dfu_res = self.enter_dfu_mode_automatically(wait_timeout_s=8.0)
        if not dfu_res.get("success"):
            err_msg = dfu_res.get("error", "Cihaz otomatik DFU moduna gecirilemedi.")
            res = {
                "success": False,
                "code": dfu_res.get("code", "DFU_TRANSITION_FAILED"),
                "old_version": old_ver,
                "target_version": target_ver,
                "error": err_msg
            }
            self._update_fw_status(False, "error", 0, err_msg, error=err_msg, result=res)
            return res

        # Step 4: Flash firmware via DFU and auto-reset
        self._update_fw_status(True, "flashing", 50, f"Firmware (v{target_ver}) STM32 bellegine yaziliyor...")
        if self._sim_hooks and "flash_dfu" in self._sim_hooks:
            flash_res = self._sim_hooks["flash_dfu"](hex_path, target_ver)
        else:
            cli_path = self._find_stm32_programmer_cli()
            dfu_util_path = self._find_dfu_util()
            if cli_path:
                flash_res = self._flash_with_stm32cube_cli(
                    cli_path,
                    hex_path,
                    progress_cb=lambda p, m: self._update_fw_status(True, "flashing", p, m)
                )
            elif dfu_util_path:
                flash_res = self._flash_with_dfu_util(
                    dfu_util_path,
                    hex_path,
                    progress_cb=lambda p, m: self._update_fw_status(True, "flashing", p, m)
                )
            else:
                flash_res = {
                    "success": False,
                    "code": "NO_DFU_TOOL",
                    "error": "DFU programlama araci (STM32CubeProgrammer / dfu-util) bulunamadi."
                }

        if not flash_res.get("success"):
            err_msg = flash_res.get("error", "Firmware yazma islemi basarisiz oldu.")
            res = {
                "success": False,
                "code": flash_res.get("code", "FLASH_FAILED"),
                "old_version": old_ver,
                "target_version": target_ver,
                "error": err_msg
            }
            self._update_fw_status(False, "error", 0, err_msg, error=err_msg, result=res)
            return res

        # Step 5: Reconnect to normal mode and verify new version matches target_ver
        self._update_fw_status(True, "verifying", 85, "Cihaz yeniden baslatildi, surum dogrulaniyor...")
        verified_ver = ""
        t0 = time.time()
        reconnect_timeout = 10.0 if not self._sim_hooks else 1.5
        while time.time() - t0 < reconnect_timeout:
            if not self._sim_hooks:
                time.sleep(0.4)
            ver_check = self.read_device_firmware_version()
            if ver_check.get("connected") and ver_check.get("device_version"):
                verified_ver = ver_check["device_version"]
                break
            if self._sim_hooks:
                break

        if not verified_ver:
            err_msg = "Firmware yuklendi ancak cihaz normal modda yeniden baglanamadi (Baglanti koptu)."
            res = {
                "success": False,
                "code": "RECONNECT_TIMEOUT",
                "old_version": old_ver,
                "target_version": target_ver,
                "error": err_msg
            }
            self._update_fw_status(False, "error", 0, err_msg, error=err_msg, result=res)
            return res

        if parse_version_tuple(verified_ver) != parse_version_tuple(target_ver):
            err_msg = (
                f"Surum dogrulamasi basarisiz! Beklenen surum: v{target_ver}, "
                f"cihazdan okunan surum: v{verified_ver}."
            )
            res = {
                "success": False,
                "code": "VERSION_MISMATCH",
                "old_version": old_ver,
                "new_version": verified_ver,
                "target_version": target_ver,
                "error": err_msg
            }
            self._update_fw_status(False, "error", 0, err_msg, error=err_msg, result=res)
            return res

        ok_msg = f"Cihaz basariyla v{verified_ver} surumune guncellendi ve dogrulandi."
        res = {
            "success": True,
            "code": "UPDATED_AND_VERIFIED",
            "old_version": old_ver,
            "new_version": verified_ver,
            "target_version": target_ver,
            "hex_filename": hex_filename,
            "verified": True,
            "message": ok_msg
        }
        self._update_fw_status(False, "done", 100, ok_msg, error=None, result=res)
        return res

    # ------------------------------------------------------------------
    # FAZ 2: nRF24L01 2.4GHz Wireless Accessory Receiver Status & Config
    # ------------------------------------------------------------------
    def get_nrf24_status(self):
        """
        Queries STM32 nRF24L01 status via `sys.nrfstatus?`.
        Format returned by firmware: present:enabled:channel:rate:pa:rx_count:buttons:irq:status_reg
        Works seamlessly whether the nRF24L01 module is plugged in or not.
        """
        pinout = {
            "sck": "PB13 (SPI2_SCK)",
            "miso": "PB14 (SPI2_MISO)",
            "mosi": "PB15 (SPI2_MOSI)",
            "ce": "PB6 (GPIO Output)",
            "csn": "PB7 (GPIO Output)",
            "irq": "PB9 (GPIO Input, Pull-Up)"
        }
        rate_labels = {0: "250 kbps", 1: "1 Mbps", 2: "2 Mbps"}
        pa_labels = {0: "-18 dBm (Dusuk)", 1: "-12 dBm (Orta)", 2: "-6 dBm (Yuksek)", 3: "0 dBm (Maksimum)"}

        raw = ""
        device_connected = False
        if self._sim_hooks and "read_nrf_status" in self._sim_hooks:
            sim_res = self._sim_hooks["read_nrf_status"]()
            device_connected = sim_res.get("connected", False)
            raw = sim_res.get("raw", "")
        elif self._ser and self._ser.is_open:
            device_connected = True
            res = self.serial_send_command("sys.nrfstatus?\n", wait_ms=80)
            if res.get("success"):
                raw = res.get("response", "")

        if not device_connected:
            return {
                "success": True,
                "device_connected": False,
                "hw_present": False,
                "enabled": True,
                "channel": 76,
                "freq_mhz": 2476,
                "data_rate": 1,
                "data_rate_label": rate_labels[1],
                "pa_level": 2,
                "pa_level_label": pa_labels[2],
                "rx_packets": 0,
                "buttons_mask": 0,
                "irq_pin": 1,
                "status_reg": 255,
                "pinout": pinout,
                "summary": "STM32 cihazi bagli degil"
            }

        # Parse response like [sys.nrfstatus|1:1:76:1:2:140:0:1:14] or 0:1:76:1:2:0:0:1:255
        m = re.search(r'(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+):(\d+)', raw)
        if m:
            hw_present = int(m.group(1)) == 1
            enabled = int(m.group(2)) == 1
            channel = int(m.group(3))
            data_rate = int(m.group(4))
            pa_level = int(m.group(5))
            rx_packets = int(m.group(6))
            buttons_mask = int(m.group(7))
            irq_pin = int(m.group(8))
            status_reg = int(m.group(9))
        else:
            hw_present = False
            enabled = True
            channel = 76
            data_rate = 1
            pa_level = 2
            rx_packets = 0
            buttons_mask = 0
            irq_pin = 1
            status_reg = 255

        if not enabled:
            summary = "Devre Disi (Kullanici tarafindan kapatildi)"
        elif hw_present:
            summary = f"Bagli ve Aktif ({2400 + channel} MHz, {rate_labels.get(data_rate, '1 Mbps')})"
        else:
            summary = "Modul Takili Degil — Cihaz Standart Kablolu Modda Sorunsuz Calisiyor"

        return {
            "success": True,
            "device_connected": True,
            "hw_present": hw_present,
            "enabled": enabled,
            "channel": channel,
            "freq_mhz": 2400 + channel,
            "data_rate": data_rate,
            "data_rate_label": rate_labels.get(data_rate, "1 Mbps"),
            "pa_level": pa_level,
            "pa_level_label": pa_labels.get(pa_level, "-6 dBm (Yuksek)"),
            "rx_packets": rx_packets,
            "buttons_mask": buttons_mask,
            "irq_pin": irq_pin,
            "status_reg": status_reg,
            "pinout": pinout,
            "summary": summary
        }

    def configure_nrf24(self, enabled=True, channel=76, data_rate=1, pa_level=2):
        """Updates nRF24L01 configuration in settings.json and sends commands to STM32 if connected."""
        ch = max(0, min(125, int(channel)))
        rate = max(0, min(2, int(data_rate)))
        pa = max(0, min(3, int(pa_level)))
        en = 1 if enabled else 0

        self.save_settings({
            "nrf24_enabled": bool(en),
            "nrf24_channel": ch,
            "nrf24_data_rate": rate,
            "nrf24_pa_level": pa
        })

        cmds = [
            f"sys.nrfen={en}\n",
            f"sys.nrfch={ch}\n",
            f"sys.nrfrate={rate}\n",
            f"sys.nrfpa={pa}\n"
        ]
        if self._sim_hooks and "write_nrf_config" in self._sim_hooks:
            self._sim_hooks["write_nrf_config"](en, ch, rate, pa)
        elif self._ser and self._ser.is_open:
            for c in cmds:
                self.serial_send_command(c, wait_ms=40)

        return self.get_nrf24_status()

    # ------------------------------------------------------------------
    # GitHub App Release Update Check
    # ------------------------------------------------------------------
    def check_update(self, current_version=None):
        if not current_version:
            current_version = load_version_config()["version"]
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

                download_url = f"https://github.com/{REPO}/releases/latest"
                hex_download_url = ""
                hex_asset_name = ""
                for asset in data.get("assets", []):
                    aname = asset.get("name", "")
                    if aname.lower().endswith(".exe"):
                        download_url = asset.get("browser_download_url")
                    elif aname.lower().endswith(".hex"):
                        hex_download_url = asset.get("browser_download_url")
                        hex_asset_name = aname

                has_update = is_newer_version(latest_tag, current_version)
                return {
                    "success": True,
                    "has_update": has_update,
                    "latest_tag": latest_tag,
                    "current_version": current_version,
                    "body": body,
                    "download_url": download_url,
                    "hex_download_url": hex_download_url,
                    "hex_asset_name": hex_asset_name
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def perform_silent_update(self, download_url):
        try:
            live_html = get_html_path()
            timestamp = int(time.time())
            html_url = f"https://raw.githubusercontent.com/{REPO}/main/index.html?t={timestamp}"
            headers = {"User-Agent": "VelocityControlHubApp"}
            req = urllib.request.Request(html_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                new_html = resp.read()
                with open(live_html, 'wb') as f:
                    f.write(new_html)
            return {"success": True, "live_html": live_html}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def reload_window(self):
        try:
            live_html = get_html_path()
            if self._window:
                self._window.load_url(f'file:///{live_html.replace("\\", "/")}')
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_external(self, url):
        webbrowser.open(url)
        return {"success": True}


def get_html_path():
    app_data_dir = os.path.join(get_app_data_dir(), 'app')
    os.makedirs(app_data_dir, exist_ok=True)
    live_html = os.path.join(app_data_dir, 'index.html')

    bundle_dir = get_base_dir()
    vcfg = load_version_config(bundle_dir)

    def _digest(path):
        try:
            with open(path, 'rb') as fh:
                return hashlib.md5(fh.read()).hexdigest()
        except Exception:
            return None

    assets = ['pro_wheel.png', 'wheel.png', 'version.json', vcfg["firmware_hex"]]
    for asset in assets:
        src = os.path.join(bundle_dir, asset)
        if not os.path.exists(src):
            src = os.path.join(bundle_dir, 'Firmware', asset)
        dst = os.path.join(app_data_dir, asset)
        if os.path.exists(src) and _digest(src) != _digest(dst):
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
        if not is_newer_version(live_ver, bundled_ver) and _digest(bundled_html) != _digest(live_html):
            try:
                shutil.copy2(bundled_html, live_html)
            except Exception:
                pass

    return live_html if os.path.exists(live_html) else bundled_html


def main():
    live_html = get_html_path()
    api = HubApi()
    if not WEBVIEW_OK:
        raise RuntimeError("pywebview yuklu degil")
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
