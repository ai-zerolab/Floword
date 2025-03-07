"""Backend process manager for the Floword UI."""

import asyncio
import os
import socket
import sys
from typing import Dict, Optional, Tuple

from floword.ui.models import BackendConfig


class BackendProcessManager:
    """Manager for the backend process."""

    def __init__(self):
        """Initialize the backend process manager."""
        self.process: Optional[asyncio.subprocess.Process] = None
        self.port: Optional[int] = None
        self.env_vars: Dict[str, str] = {}
        self._stderr_reader_task = None

    async def is_port_available(self, port: int) -> bool:
        """Check if a port is available.

        Args:
            port: The port to check.

        Returns:
            True if the port is available, False otherwise.
        """
        try:
            # Create a socket and try to bind to the port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("localhost", port))
            sock.close()
            return True
        except OSError:
            return False

    async def find_available_port(self, start_port: int = 9772) -> int:
        """Find an available port starting from start_port.

        Args:
            start_port: The port to start searching from.

        Returns:
            An available port.
        """
        port = start_port
        while not await self.is_port_available(port):
            port += 1
        return port

    async def _read_stderr(self, stderr_stream):
        """Read from stderr and redirect to sys.stderr.

        Args:
            stderr_stream: The stderr stream to read from.
        """
        while True:
            line = await stderr_stream.readline()
            if not line:
                break
            sys.stderr.write(f"[Backend] {line.decode()}")
            sys.stderr.flush()

    async def start_backend(self, port: int, env_vars: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
        """Start the backend process.

        Args:
            port: The port to start the backend on.
            env_vars: Optional environment variables to pass to the backend.

        Returns:
            A tuple of (success, message).
        """
        if self.process and self.process.returncode is None:
            return False, "Backend is already running"

        # Check if the port is available
        if not await self.is_port_available(port):
            return False, f"Port {port} is not available"

        # Prepare environment variables
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
            self.env_vars = env_vars

        # Start the backend process
        try:
            self.process = await asyncio.create_subprocess_exec(
                "floword",
                "start",
                "--port",
                str(port),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.port = port

            # Start a task to read stderr and redirect it
            self._stderr_reader_task = asyncio.create_task(self._read_stderr(self.process.stderr))

            # Wait a bit to see if the process starts successfully
            await asyncio.sleep(1)

            if self.process.returncode is not None:
                stderr = await self.process.stderr.read()
                return False, f"Backend failed to start: {stderr.decode()}"

            return True, f"Backend started on port {port}"
        except Exception as e:
            return False, f"Error starting backend: {str(e)}"

    async def stop_backend(self) -> Tuple[bool, str]:
        """Stop the backend process.

        Returns:
            A tuple of (success, message).
        """
        if not self.process or self.process.returncode is not None:
            return False, "Backend is not running"

        try:
            # Cancel the stderr reader task if it exists
            if self._stderr_reader_task:
                self._stderr_reader_task.cancel()
                try:
                    await self._stderr_reader_task
                except asyncio.CancelledError:
                    pass
                self._stderr_reader_task = None

            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                return True, "Backend stopped"
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
                return True, "Backend killed after timeout"
        except Exception as e:
            return False, f"Error stopping backend: {str(e)}"

    async def get_backend_status(self) -> Tuple[bool, str]:
        """Get the status of the backend process.

        Returns:
            A tuple of (running, status_message).
        """
        if not self.process:
            return False, "Backend not started"

        if self.process.returncode is None:
            return True, f"Backend running on port {self.port}"
        else:
            return False, f"Backend exited with code {self.process.returncode}"

    def get_backend_url(self) -> str:
        """Get the URL of the backend.

        Returns:
            The URL of the backend.
        """
        if self.port:
            return f"http://localhost:{self.port}"
        return "http://localhost:9772"  # Default
