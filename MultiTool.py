import os
import sys
import subprocess
import string
import getpass
import threading
import ctypes
from pathlib import Path

import tkinter as tk
from tkinter import scrolledtext

from PIL import Image
import pystray
from pystray import MenuItem as item


# ================== ПУТИ ==================
def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.resolve()


BASE_DIR = get_base_dir()
INSTALLERS_DIR = BASE_DIR / "bin" / "downloaders"
AUTORUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTORUN_NAME = "MultiTool"


# ================== СПИСОК ПРОГРАММ ==================
APPS = {
    "PowerShell (Обычный)": (
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        None, False, None
    ),
    "PowerShell (Админ)": (
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        None, True, None
    ),
    "CMD (Обычный)": (
        r"C:\Windows\System32\cmd.exe",
        None, False, None
    ),
    "CMD (Админ)": (
        r"C:\Windows\System32\cmd.exe",
        None, True, None
    ),
    "CrystalDisk": (
        None,
        "CrystalDiskInfo.exe", False, "DiskInfo64.exe"
    ),
    "Process Hacker 2": (
        None,
        "processhacker.exe", True, "ProcessHacker.exe"
    ),
    "Revo Uninstaller": (
        None,
        "revosetup.exe", False, "RevoUninPro.exe"
    ),
    "AnyDesk": (
        None,
        None, False, "AnyDesk.exe"
    ),
    "Radmin": (
        None,
        "Radmin_Viewer_3.5.2.1_RU.msi", False, "Radmin.exe"
    ),
    "Диспетчер задач": (
        r"C:\Windows\System32\taskmgr.exe",
        None, True, None
    ),
    "Rufus": (
        None,
        None, False, "rufus.exe"
    ),
    "DDU (Display Driver Uninstaller)": (
        None,
        "DDU_setup.exe", True, "Display Driver Uninstaller.exe"
    ),
}


# ================== АВТОЗАПУСК ==================
def get_launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if pythonw.exists():
        return f'"{pythonw}" "{Path(__file__).resolve()}"'
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'


def is_autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTORUN_KEY) as key:
            try:
                winreg.QueryValueEx(key, AUTORUN_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def set_autostart(enabled):
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, AUTORUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, AUTORUN_NAME, 0, winreg.REG_SZ, get_launch_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, AUTORUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        log(f"[!] Ошибка настройки автозапуска: {e}")
        return False


def toggle_autostart(icon=None, itm=None):
    current = is_autostart_enabled()
    if set_autostart(not current):
        state = "включён" if not current else "выключен"
        log(f"[*] Автозапуск {state}.")


# ================== ГЛОБАЛЬНАЯ ССЫЛКА ==================
app = None


# ================== ЛОГ ==================
def log(message):
    if app is not None and app.log_widget is not None:
        try:
            app.log_widget.configure(state="normal")
            app.log_widget.insert("end", message + "\n")
            app.log_widget.see("end")
            app.log_widget.configure(state="disabled")
        except Exception:
            pass


def print_banner():
    username = getpass.getuser()
    line = "=" * 62
    log(line)
    log(f"  Приветствую, {username}!")
    log("  Это программа для быстрого использования вспомогательных")
    log("  инструментов.")
    log(line)
    log("")
    log("  Ниже будут отображаться логи поиска программ или установки")
    log("  программ.")
    log("")
    log(line)
    log("  Приложение запущено в трее...")
    log("  Приятного использования!")
    log("")
    log("  make by yuoin 2026")
    log(line)
    log("")


# ================== ЗАПУСК ==================
def run_with_admin(path):
    try:
        subprocess.run(
            ["powershell", "-Command",
             f"Start-Process -FilePath '{path}' -Verb RunAs"]
        )
    except Exception as e:
        log(f"[!] Ошибка admin-запуска: {e}")


def run_normal(path):
    try:
        subprocess.Popen(
            [str(path)],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    except OSError as e:
        # WinError 740 — требуется повышение прав
        if getattr(e, "winerror", None) == 740:
            log(f"    [!] Требуются права администратора, перезапуск с UAC...")
            run_with_admin(str(path))
        else:
            log(f"[!] Ошибка запуска: {e}")
    except Exception as e:
        log(f"[!] Ошибка запуска: {e}")


# ================== ПОИСК В DOWNLOADERS (ГИБКИЙ) ==================
def find_portable_in_downloaders(exe_name):
    if not INSTALLERS_DIR.is_dir():
        return None
    base = os.path.splitext(exe_name.lower())[0]
    exact = INSTALLERS_DIR / exe_name
    if exact.exists():
        return str(exact)
    try:
        for f in INSTALLERS_DIR.iterdir():
            if not f.is_file():
                continue
            name = f.name.lower()
            if name.endswith(".exe") and name.startswith(base):
                return str(f)
    except Exception:
        pass
    return None


# ================== ПОИСК: APP PATHS ==================
def find_in_app_paths(exe_name):
    try:
        import winreg
    except ImportError:
        return None
    if not exe_name:
        return None
    locations = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
    for hive, subkey in locations:
        try:
            with winreg.OpenKey(hive, f"{subkey}\\{exe_name}") as key:
                path, _ = winreg.QueryValueEx(key, "")
                path = path.strip('"').strip()
                if path and os.path.exists(path):
                    return path
        except (FileNotFoundError, OSError):
            continue
    return None


# ================== ПОИСК: UNINSTALL ==================
def find_in_uninstall(exe_name):
    try:
        import winreg
    except ImportError:
        return None
    if not exe_name:
        return None
    uninstall_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, subkey in uninstall_keys:
        try:
            with winreg.OpenKey(hive, subkey) as root:
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(root, i)
                        i += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(root, sub_name) as sub:
                            install_loc = None
                            try:
                                install_loc, _ = winreg.QueryValueEx(sub, "InstallLocation")
                            except FileNotFoundError:
                                pass
                            if install_loc and os.path.isdir(install_loc):
                                r = search_exe_recursive(install_loc, exe_name, depth=2)
                                if r:
                                    return r
                            try:
                                di, _ = winreg.QueryValueEx(sub, "DisplayIcon")
                                if di:
                                    clean = di.split(",")[0].strip('"')
                                    if clean.lower().endswith(".exe") and os.path.exists(clean):
                                        if Path(clean).name.lower() == exe_name.lower():
                                            return clean
                            except FileNotFoundError:
                                pass
                    except Exception:
                        continue
        except Exception:
            continue
    return None


# ================== ПОИСК: МЕНЮ ПУСК ==================
def resolve_lnk(lnk_path):
    try:
        import pythoncom
        from win32com.shell import shell
        shortcut = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None,
            pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
        )
        shortcut.QueryInterface(pythoncom.IID_IPersistFile).Load(lnk_path)
        path, _ = shortcut.GetPath(shell.SLGP_UNCPRIORITY)
        return path
    except Exception:
        pass
    try:
        ps = ("$sh = New-Object -ComObject WScript.Shell; "
              f"$sh.CreateShortcut('{lnk_path}').TargetPath")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None
    except Exception:
        return None


def find_in_start_menu(exe_name):
    if not exe_name:
        return None
    dirs = [
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
    ]
    target = exe_name.lower()
    base = os.path.splitext(target)[0]
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for dp, _, files in os.walk(d):
            for f in files:
                if not f.lower().endswith(".lnk"):
                    continue
                n = os.path.splitext(f)[0].lower()
                if base in n or n in base:
                    p = os.path.join(dp, f)
                    r = resolve_lnk(p)
                    if r and os.path.exists(r) and Path(r).name.lower() == target:
                        return r
    return None


# ================== ПОИСК: ПО ДИСКУ ==================
def search_exe_recursive(root_dir, exe_name, depth=3):
    if not os.path.isdir(root_dir):
        return None
    target = exe_name.lower()
    try:
        for dp, dn, fn in os.walk(root_dir):
            cd = dp[len(root_dir):].count(os.sep)
            if cd >= depth:
                dn[:] = []
                continue
            for f in fn:
                if f.lower() == target:
                    return os.path.join(dp, f)
    except (PermissionError, FileNotFoundError):
        pass
    return None


def find_on_disk(exe_name):
    if not exe_name:
        return None
    roots = [
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        os.path.expandvars(r"%APPDATA%"),
    ]
    for r in roots:
        if os.path.isdir(r):
            res = search_exe_recursive(r, exe_name, 2)
            if res:
                return res
    for letter in string.ascii_uppercase:
        if letter == "C":
            continue
        drive = f"{letter}:\\"
        if not os.path.exists(drive):
            continue
        log(f"    [*] Поиск на диске {drive}")
        res = search_exe_recursive(drive, exe_name, 3)
        if res:
            return res
    return None


# ================== УНИВЕРСАЛЬНЫЙ ПОИСК ==================
def resolve_program_path(default_path, exe_name, is_portable=False):
    if default_path and os.path.exists(str(default_path)):
        return str(default_path)

    if not exe_name:
        return None

    if is_portable:
        portable = find_portable_in_downloaders(exe_name)
        if portable:
            log(f"    [downloaders] {portable}")
            return portable

    p = find_in_app_paths(exe_name)
    if p:
        log(f"    [реестр App Paths] {p}")
        return p

    log(f"    [*] Поиск в Uninstall: {exe_name}")
    p = find_in_uninstall(exe_name)
    if p:
        log(f"    [реестр Uninstall] {p}")
        return p

    log(f"    [*] Поиск в меню Пуск: {exe_name}")
    p = find_in_start_menu(exe_name)
    if p:
        log(f"    [меню Пуск] {p}")
        return p

    log(f"    [*] Поиск по диску: {exe_name}")
    p = find_on_disk(exe_name)
    if p:
        log(f"    [диск] {p}")
        return p

    return None


# ================== ЗАПУСК ПРОГРАММЫ ==================
def launch_app(app_name, program_path, installer_name=None,
               as_admin=False, exe_name=None):
    if app is not None:
        app.set_tray_icon(active=True)
    try:
        log(f"\n[>] {app_name}")

        is_portable = (installer_name is None)
        resolved = resolve_program_path(program_path, exe_name, is_portable)

        if resolved:
            log(f"[+] Запуск: {resolved}")
            if as_admin:
                run_with_admin(resolved)
            else:
                run_normal(resolved)
            return

        if installer_name:
            ip = INSTALLERS_DIR / installer_name
            if ip.exists():
                log(f"[!] Не найдена. Запуск установщика: {installer_name}")
                if ip.suffix.lower() == ".msi":
                    try:
                        subprocess.run(
                            ["powershell", "-Command",
                             f"Start-Process msiexec.exe "
                             f"-ArgumentList '/i \"{ip}\"' -Verb RunAs"]
                        )
                    except Exception as e:
                        log(f"[!] Ошибка запуска MSI: {e}")
                else:
                    run_with_admin(str(ip))
                return
            log(f"[!] Установщик не найден: {ip}")
        else:
            log(f"[!] Файл не найден в downloaders: {exe_name}")

        log(f"[-] Ничего не найдено для: {app_name}")
    finally:
        if app is not None:
            app.set_tray_icon(active=False)


# ================== ГЛАВНОЕ ОКНО ==================
class MultiToolWindow:
    def __init__(self, root):
        self.root = root
        self.tray_icon = None
        self.log_widget = None
        self._tray_started = False
        self._icon_normal = None
        self._icon_active = None

        self.root.title("MultiTool")
        self.root.geometry("720x520")
        self.root.minsize(560, 400)
        self.root.configure(bg="#0c0c0c")

        self.root.after(100, self._hide_from_taskbar)

        icon_path = BASE_DIR / "icon.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.bind("<Unmap>", self.on_unmap)

    def _hide_from_taskbar(self):
        try:
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080

            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def _build_ui(self):
        tk.Label(
            self.root, text="MultiTool",
            bg="#0c0c0c", fg="#ffffff",
            font=("Consolas", 12, "bold"),
        ).pack(anchor="w", padx=10, pady=(10, 0))

        tk.Label(
            self.root, text="Меню программ — в трее (правый клик по иконке)",
            bg="#0c0c0c", fg="#888888",
            font=("Consolas", 9),
        ).pack(anchor="w", padx=10, pady=(0, 6))

        self.log_widget = scrolledtext.ScrolledText(
            self.root,
            bg="#0c0c0c", fg="#cccccc",
            insertbackground="#cccccc",
            font=("Consolas", 9),
            relief="flat",
            state="disabled",
            wrap="word",
        )
        self.log_widget.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        bottom = tk.Frame(self.root, bg="#0c0c0c")
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        tk.Button(
            bottom, text="Свернуть в трей",
            font=("Consolas", 9),
            bg="#1e1e1e", fg="#dddddd",
            activebackground="#2d2d2d", activeforeground="#ffffff",
            relief="flat", padx=10, pady=4,
            command=self.hide_to_tray,
        ).pack(side="left")

        tk.Button(
            bottom, text="Выход",
            font=("Consolas", 9),
            bg="#1e1e1e", fg="#dddddd",
            activebackground="#2d2d2d", activeforeground="#ffffff",
            relief="flat", padx=10, pady=4,
            command=self.quit_app,
        ).pack(side="right")

        tk.Label(
            bottom, text="make by yuoin 2026",
            bg="#0c0c0c", fg="#666666",
            font=("Consolas", 8),
        ).pack(side="left", padx=12)

    def _launch(self, name, path, installer, as_admin, exe_name):
        threading.Thread(
            target=launch_app,
            args=(name, path, installer, as_admin, exe_name),
            daemon=True,
        ).start()

    def on_unmap(self, event):
        if self.root.state() == "iconic":
            self.hide_to_tray()

    def hide_to_tray(self):
        self.root.withdraw()
        self._start_tray()

    def _start_tray(self):
        if self._tray_started:
            return
        self._tray_started = True

        self._icon_normal = self._load_tray_image("icon.ico", "icon.png")
        self._icon_active = self._load_tray_image(
            "icon_active.ico", "icon_active.png"
        ) or self._icon_normal

        autostart_item = item(
            "Автозапуск при входе в Windows",
            toggle_autostart,
            checked=lambda itm: is_autostart_enabled(),
        )

        menu_items = [
            item("Открыть", self.show_window, default=True),
            pystray.Menu.SEPARATOR,
        ]
        for name, (path, installer, as_admin, exe_name) in APPS.items():
            menu_items.append(
                item(name, self._make_tray_cb(name, path, installer, as_admin, exe_name))
            )
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(autostart_item)
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(item("Выход", self.quit_app))

        menu = pystray.Menu(*menu_items)
        self.tray_icon = pystray.Icon(
            "MultiTool", self._icon_normal, "Мультитул", menu
        )
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def set_tray_icon(self, active):
        if self.tray_icon is None:
            return
        try:
            target = self._icon_active if active else self._icon_normal
            if target is not None:
                self.tray_icon.icon = target
        except Exception:
            pass

    def _make_tray_cb(self, name, path, installer, as_admin, exe_name):
        def cb(icon, itm):
            self._launch(name, path, installer, as_admin, exe_name)
        return cb

    def _load_tray_image(self, *names):
        for name in names:
            p = BASE_DIR / name
            if p.exists():
                try:
                    return Image.open(p).convert("RGBA")
                except Exception:
                    continue
        return None

    def show_window(self, icon=None, itm=None):
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        self._tray_started = False
        self.root.after(0, self._do_show)

    def _do_show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self, icon=None, itm=None):
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.after(0, self.root.destroy)


# ================== ЗАПУСК ==================
def main():
    global app
    root = tk.Tk()
    app = MultiToolWindow(root)
    print_banner()
    app._start_tray()
    root.mainloop()


if __name__ == "__main__":
    main()