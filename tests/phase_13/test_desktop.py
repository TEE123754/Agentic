"""Windows native phase boundary; only disposable synthetic secrets are used."""

import sys
import time
import uuid
from unittest.mock import patch

import httpx
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Native Windows gate")


def test_windows_native_credentials_roundtrip():
    from frictionlab.credentials import secure_backend

    backend = secure_backend()
    service = "FrictionLab-Acceptance-" + str(uuid.uuid4())
    secret = "SYNTHETIC_ACCEPTANCE_ONLY_123456789"
    try:
        backend.set_password(service, "test", secret)
        assert backend.get_password(service, "test") == secret
    finally:
        if backend.get_password(service, "test"):
            backend.delete_password(service, "test")
    assert backend.get_password(service, "test") is None


def test_native_window_key_mask_and_service_lifecycle(tmp_path):
    import tkinter as tk
    from tkinter import messagebox, ttk

    from frictionlab.app import Connection, connect
    from frictionlab.assessment.service import read_settings
    from frictionlab.credentials import _SESSION
    from frictionlab.desktop import Desktop
    from frictionlab.launcher import LocalServer

    root = tk.Tk()
    root.withdraw()
    _SESSION.clear()
    app = None
    try:
        app = Desktop(
            root,
            tk,
            ttk,
            messagebox,
            tmp_path,
            LocalServer,
            connect,
            Connection,
            lambda: True,
            read_settings,
        )
        assert app.key_entry.cget("show") == "●"
        app.key.set("gsk_SYNTHETIC_DESKTOP_ONLY_123456789")
        app.model.set("fixture-model")
        app.sharing.set(True)
        app.free.set(True)
        app.configure()
        assert app.key.get() == ""
        assert "SYNTHETIC" not in (tmp_path / "app-settings.json").read_text()
        with patch("webbrowser.open") as opened:
            app.start()
            for _ in range(200):
                root.update()
                if app.server.ready:
                    break
                time.sleep(0.05)
            assert app.server.ready
            app.open()
            assert opened.called
            assert httpx.get(app.server.url, trust_env=False).status_code == 200
        app.stop()
        app.server.thread.join(60)
        assert not app.server.thread.is_alive()
    finally:
        if app and app.server:
            app.stop()
            app.server.thread.join(60)
        _SESSION.clear()
        root.destroy()
