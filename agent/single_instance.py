import socket
import threading
import sys

_server_socket = None
_show_callback = None
LOCK_PORT = 9002


def _listen_for_signals() -> None:
    global _server_socket
    while True:
        try:
            conn, _ = _server_socket.accept()
            conn.settimeout(2)
            try:
                data = conn.recv(64).decode("utf-8", errors="ignore").strip()
                if data == "show" and _show_callback is not None:
                    try:
                        _show_callback()
                    except Exception:
                        pass
            except (OSError, UnicodeError):
                pass
            finally:
                conn.close()
        except Exception:
            break


def try_acquire(on_show_callback) -> bool:
    """
    Try to become the single instance.
    Returns True if this is the first instance (lock acquired).
    Returns False if another instance is running (signal sent, caller should exit).
    on_show_callback is called on the main instance when a second instance requests focus.
    """
    global _server_socket, _show_callback
    _show_callback = on_show_callback

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind(("127.0.0.1", LOCK_PORT))
        sock.listen(5)
        _server_socket = sock
        thread = threading.Thread(target=_listen_for_signals, daemon=True)
        thread.start()
        return True
    except OSError:
        sock.close()
        try:
            signal_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            signal_sock.settimeout(2)
            signal_sock.connect(("127.0.0.1", LOCK_PORT))
            signal_sock.sendall(b"show")
            signal_sock.close()
        except Exception:
            pass
        return False


def release() -> None:
    global _server_socket
    if _server_socket is not None:
        try:
            _server_socket.close()
        except Exception:
            pass
        _server_socket = None
