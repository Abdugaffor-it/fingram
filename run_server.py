import os
import signal
import subprocess
import sys
import termios
import threading
import tty
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def load_env():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


load_env()
PORT = int(os.environ.get("PORT", "8000"))


def kill_port(port: int):
    try:
        output = subprocess.check_output(["lsof", "-ti", f":{port}"]).decode().strip()
    except Exception:
        output = ""
    if output:
        for pid in output.split():
            try:
                os.kill(int(pid), signal.SIGKILL)
            except Exception:
                pass
        return
    try:
        subprocess.run(["fuser", "-k", f"{port}/tcp"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def watch_hotkey(stop_event: threading.Event, proc: subprocess.Popen):
    if not sys.stdin.isatty():
        return
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while not stop_event.is_set():
            ch = sys.stdin.read(1)
            if ch == "\x11":  # Ctrl+Q
                stop_event.set()
                try:
                    proc.terminate()
                except Exception:
                    pass
                time.sleep(0.2)
                if proc.poll() is None:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                kill_port(PORT)
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def main():
    env = os.environ.copy()
    proc = subprocess.Popen([sys.executable, "app.py"], env=env)
    stop_event = threading.Event()
    thread = threading.Thread(target=watch_hotkey, args=(stop_event, proc), daemon=True)
    thread.start()
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()


if __name__ == "__main__":
    print("Server running. Press Ctrl+Q to stop and free the port.")
    main()
