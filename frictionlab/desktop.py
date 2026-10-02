"""Small native launcher: masked BYOK setup and the shared local dashboard."""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path


def main():
    if "--serve-smoke" in sys.argv:
        from frictionlab.desktop_acceptance import smoke

        return smoke()
    if "--self-check" in sys.argv:
        from frictionlab.configuration import ASSET_ROOT
        from frictionlab.launcher import LocalServer

        assert (ASSET_ROOT / "vendor" / "axe-core").is_dir()
        assert (Path(__file__).parent / "web" / "index.html").is_file()
        server = LocalServer(Path.cwd() / "self-check-workspace")
        server.socket.close()
        print("FrictionLab desktop self-check passed")
        return 0
    import tkinter as tk
    from tkinter import messagebox, ttk

    from frictionlab.app import Connection, connect
    from frictionlab.assessment.service import read_settings
    from frictionlab.credentials import storage_available
    from frictionlab.launcher import LocalServer, workspace

    root = tk.Tk()
    root.title("FrictionLab — Local website testing")
    root.geometry("600x670")
    root.minsize(520, 600)
    app = Desktop(
        root,
        tk,
        ttk,
        messagebox,
        workspace(),
        LocalServer,
        connect,
        Connection,
        storage_available,
        read_settings,
    )
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()
    return 0


class Desktop:
    def __init__(
        self,
        root,
        tk,
        ttk,
        messagebox,
        workspace,
        server_class,
        connect,
        connection_class,
        storage_available,
        read_settings,
    ):
        self.root, self.tk, self.dialog = root, tk, messagebox
        self.workspace, self.server_class, self.connect, self.connection_class = (
            workspace,
            server_class,
            connect,
            connection_class,
        )
        self.server = None
        self.closing = False
        frame = ttk.Frame(root, padding=28)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="FrictionLab", font=("Segoe UI", 24, "bold")).pack(anchor="w")
        ttk.Label(
            frame, text="Local website assessment · Your API key", font=("Segoe UI", 11)
        ).pack(anchor="w", pady=(0, 18))
        ttk.Label(frame, text="Connect your AI provider", font=("Segoe UI", 13, "bold")).pack(
            anchor="w"
        )
        self.provider = tk.StringVar(value="groq")
        self.model = tk.StringVar()
        self.key = tk.StringVar()
        self.remember = tk.BooleanVar(value=False)
        self.sharing = tk.BooleanVar(value=False)
        self.free = tk.BooleanVar(value=False)
        ttk.Label(frame, text="Provider").pack(anchor="w", pady=(10, 0))
        ttk.Combobox(
            frame, textvariable=self.provider, values=("groq", "gemini"), state="readonly"
        ).pack(fill="x")
        ttk.Label(frame, text="Model identifier available to your account").pack(
            anchor="w", pady=(10, 0)
        )
        ttk.Entry(frame, textvariable=self.model).pack(fill="x")
        ttk.Label(frame, text="API key (hidden; never written to plaintext)").pack(
            anchor="w", pady=(10, 0)
        )
        self.key_entry = ttk.Entry(frame, textvariable=self.key, show="●")
        self.key_entry.pack(fill="x")
        remember = ttk.Checkbutton(
            frame, text="Remember in native OS credential store", variable=self.remember
        )
        remember.pack(anchor="w", pady=(10, 0))
        if not storage_available():
            remember.state(["disabled"])
        ttk.Checkbutton(
            frame, text="Allow redacted findings to be sent to my provider", variable=self.sharing
        ).pack(anchor="w")
        ttk.Checkbutton(
            frame, text="I verified this account/model's free-tier eligibility", variable=self.free
        ).pack(anchor="w")
        ttk.Button(frame, text="Connect key", command=self.configure).pack(fill="x", pady=(12, 0))
        ttk.Separator(frame).pack(fill="x", pady=18)
        ttk.Button(frame, text="Start local dashboard", command=self.start).pack(fill="x")
        ttk.Button(frame, text="Open dashboard", command=self.open).pack(fill="x", pady=7)
        ttk.Button(frame, text="Stop local service", command=self.stop).pack(fill="x")
        self.status = tk.StringVar(value="Ready. Structural checks do not require an API key.")
        ttk.Label(frame, textvariable=self.status, wraplength=510).pack(anchor="w", pady=12)
        ttk.Label(
            frame,
            text="Paste a URL and choose checks in the local dashboard. Uploaded snapshots make no target requests. Dynamic flows require an isolated replica; browser isolation alone cannot protect production.",
            wraplength=510,
        ).pack(anchor="w")
        try:
            current = read_settings(workspace)
            if current.provider != "local":
                self.provider.set(current.provider)
                self.model.set(current.model)
        except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
            self.status.set("Saved settings could not be read. Reconnect your provider.")

    def configure(self):
        try:
            value = self.connection_class(
                provider=self.provider.get(),
                model=self.model.get(),
                key=self.key.get(),
                remember=self.remember.get(),
                share_findings=self.sharing.get(),
                free_tier_confirmed=self.free.get(),
            )
            self.key.set("")
            self.connect(self.workspace, value)
            self.status.set("Key connected. Start the dashboard to begin an assessment.")
        except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
            self.key.set("")
            self.dialog.showerror(
                "Connection not saved",
                "Check the provider, model, key and required acknowledgements. If secure storage is unavailable, use session-only mode.",
            )

    def start(self):
        if self.server and self.server.thread and self.server.thread.is_alive():
            self.open()
            return
        try:
            self.server = self.server_class(self.workspace)
            self.server.start()
            self.status.set("Starting local service…")
            self.root.after(100, self.wait_ready)
        except Exception:  # noqa: BLE001 - Boundary faults must yield safe diagnostics, never raw secrets.
            self.status.set("Local service could not start. Check local permissions and try again.")

    def wait_ready(self):
        if not self.server or self.closing:
            return
        if self.server.ready:
            self.status.set("Running locally: " + self.server.url)
            self.open()
        elif self.server.thread.is_alive():
            self.root.after(100, self.wait_ready)
        else:
            self.status.set("Local service stopped before startup completed.")

    def open(self):
        if self.server and self.server.ready:
            webbrowser.open(self.server.url)
        else:
            self.status.set("Start the local service first.")

    def stop(self):
        if self.server:
            self.server.stop()
            self.status.set("Stopping. In-flight work is bounded; partial reports remain local.")

    def close(self):
        self.closing = True
        self.stop()

        def complete():
            if self.server and self.server.thread and self.server.thread.is_alive():
                self.root.after(100, complete)
            else:
                self.key.set("")
                self.root.destroy()

        complete()
