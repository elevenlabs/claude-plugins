"""Inter-process communication for TTS daemon."""

from __future__ import annotations

import json
import logging
import socket
import threading
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class IpcServer:
    """Unix socket server for IPC with hook handlers."""

    def __init__(self, socket_path: Path, on_message: Callable[[dict], None]):
        self.socket_path = socket_path
        self.on_message = on_message
        self._server: socket.socket | None = None
        self._running = False
        self._accept_thread: threading.Thread | None = None

    def start(self) -> None:
        """Start IPC server."""
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove stale socket file
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass

        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(str(self.socket_path))
        self._server.listen(5)
        self._server.settimeout(1.0)  # For graceful shutdown
        self._running = True

        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        logger.info("IPC server started: %s", self.socket_path)

    def stop(self) -> None:
        """Stop IPC server."""
        self._running = False

        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None

        if self._accept_thread and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=2.0)

        # Clean up socket file
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass

        logger.info("IPC server stopped")

    def _accept_loop(self) -> None:
        """Accept connections in a loop."""
        while self._running and self._server:
            try:
                conn, _ = self._server.accept()
                threading.Thread(
                    target=self._handle_client, args=(conn,), daemon=True
                ).start()
            except socket.timeout:
                continue
            except OSError:
                if self._running:
                    logger.error("Socket accept error")
                break

    def _handle_client(self, conn: socket.socket) -> None:
        """Handle a client connection."""
        try:
            data = conn.recv(65536)
            if data:
                try:
                    message = json.loads(data.decode("utf-8"))
                    self.on_message(message)
                except json.JSONDecodeError as e:
                    logger.error("Invalid JSON from client: %s", e)
        except Exception as e:
            logger.error("Error handling client: %s", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass


class IpcClient:
    """Client for sending messages to TTS daemon."""

    @staticmethod
    def send(socket_path: Path, message: dict, timeout: float = 2.0) -> bool:
        """Send message to daemon.

        Args:
            socket_path: Path to the daemon's Unix socket.
            message: Message dictionary to send.
            timeout: Connection timeout in seconds.

        Returns:
            True if message was sent successfully, False otherwise.
        """
        if not socket_path.exists():
            logger.warning("Daemon socket not found: %s", socket_path)
            return False

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(str(socket_path))
            sock.send(json.dumps(message).encode("utf-8"))
            return True
        except socket.timeout:
            logger.error("Timeout connecting to daemon")
            return False
        except ConnectionRefusedError:
            logger.error("Daemon not running (connection refused)")
            return False
        except Exception as e:
            logger.error("Failed to send message to daemon: %s", e)
            return False
        finally:
            try:
                sock.close()
            except Exception:
                pass


def get_socket_path() -> Path:
    """Get the path to the daemon's IPC socket."""
    from elevenlabs_tts.config import Config

    return Config.get_config_dir() / "daemon.sock"
