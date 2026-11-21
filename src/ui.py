"""Interface tkinter pure (stdlib) : pas de customtkinter ni Pillow => très peu de RAM."""
from __future__ import annotations

import os
import queue
import sys
import tkinter as tk
import webbrowser
from tkinter import font as tkfont

from . import startup
from .config import load_config, save_config
from .controller import ControllerEvent, PresenceController
from .paths import asset
from .roblox import get_log_directories

BG = "#08090c"
PANEL = "#111318"
PANEL_ALT = "#171a21"
INPUT_BG = "#0c0e12"
BORDER = "#2b2f39"
ACCENT = "#ef3038"
ACCENT_HOVER = "#c9222b"
TEXT = "#f4f4f5"
MUTED = "#8b909b"
OK = "#77d69a"
WARN = "#e6bd70"
BAD = "#ff777d"

FONT = "Segoe UI"


class FlatButton(tk.Label):
    """Bouton plat avec survol (tk.Button natif ignore les couleurs sous Windows)."""

    def __init__(self, master, text, command, bg, hover, fg=TEXT, bold=False, border=None, **kw):
        super().__init__(
            master,
            text=text,
            bg=bg,
            fg=fg,
            font=(FONT, 10, "bold" if bold else "normal"),
            cursor="hand2",
            highlightthickness=1 if border else 0,
            highlightbackground=border or bg,
            highlightcolor=border or bg,
            **kw,
        )
        self._command, self._bg, self._hover, self._fg = command, bg, hover, fg
        self._enabled = True
        self.bind("<Enter>", lambda _e: self._enabled and self.configure(bg=self._hover))
        self.bind("<Leave>", lambda _e: self.configure(bg=self._bg))
        self.bind("<Button-1>", lambda _e: self._enabled and self._command())

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(
            fg=self._fg if enabled else "#5a5f6b",
            bg=self._bg,
            cursor="hand2" if enabled else "arrow",
        )


class App(tk.Tk):
    def __init__(self, start_minimized: bool = False) -> None:
        super().__init__()
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.title("RBX Presence")
        self.configure(bg=BG)
        w, h = self.s(820), self.s(620)
        self.geometry(f"{w}x{h}")
        self.minsize(w, h)
        self._set_icon()

        self.config_data = load_config()
        self.events: queue.Queue[ControllerEvent] = queue.Queue()
        self.controller = PresenceController(self.events)
        self.monitoring = False
        self.game_url: str | None = None

        self.auto_monitor_var = tk.BooleanVar(value=self.config_data["auto_monitor"])
        self.autostart_var = tk.BooleanVar(value=startup.is_enabled())

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(500, self._poll_events)

        if start_minimized:
            self.iconify()
        if self.config_data["auto_monitor"] and self.config_data["client_id"].isdigit():
            self.after(300, self._start_monitoring)

    # -- helpers ------------------------------------------------------------ #
    def s(self, value: int) -> int:
        return int(value * self.scale)

    def _set_icon(self) -> None:
        try:
            if sys.platform == "win32":
                self.iconbitmap(default=str(asset("app_icon.ico")))
            else:
                self._icon = tk.PhotoImage(file=str(asset("logo_ui.png")))
                self.iconphoto(True, self._icon)
        except tk.TclError:
            pass

    def _label(self, master, text="", size=10, color=TEXT, bold=False, **kw) -> tk.Label:
        return tk.Label(
            master,
            text=text,
            fg=color,
            bg=kw.pop("bg", master["bg"]),
            font=(FONT, size, "bold" if bold else "normal"),
            **kw,
        )

    def _entry(self, master) -> tk.Entry:
        return tk.Entry(
            master,
            bg=INPUT_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=(FONT, 11),
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )

    def _check(self, master, text, variable, command) -> tk.Checkbutton:
        return tk.Checkbutton(
            master,
            text=text,
            variable=variable,
            command=command,
            bg=PANEL,
            fg=TEXT,
            activebackground=PANEL,
            activeforeground=TEXT,
            selectcolor=INPUT_BG,
            font=(FONT, 9),
            anchor="w",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )

    # -- UI ----------------------------------------------------------------- #
    def _build_ui(self) -> None:
        s = self.s
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=s(30), pady=(s(22), s(14)))
        header.grid_columnconfigure(1, weight=1)

        try:
            self._logo = tk.PhotoImage(file=str(asset("logo_ui.png")))  # 96 px
            factor = max(1, round(96 / s(52)))
            if factor > 1:
                self._logo = self._logo.subsample(factor)
            tk.Label(header, image=self._logo, bg=BG).grid(
                row=0, column=0, rowspan=2, padx=(0, s(14))
            )
        except tk.TclError:
            pass

        self._label(header, "RBX PRESENCE", 20, TEXT, True).grid(row=0, column=1, sticky="sw")
        self._label(header, "Live Roblox activity on your Discord profile", 9, MUTED).grid(
            row=1, column=1, sticky="nw"
        )
        self.badge = self._label(
            header, "●  DISCONNECTED", 9, "#c4c7cf", True, bg=PANEL_ALT, padx=s(14), pady=s(7)
        )
        self.badge.grid(row=0, column=2, rowspan=2, sticky="e")

        content = tk.Frame(self, bg=BG)
        content.grid(row=1, column=0, sticky="nsew", padx=s(30), pady=(0, s(10)))
        content.grid_columnconfigure(0, weight=4, uniform="c")
        content.grid_columnconfigure(1, weight=6, uniform="c")
        content.grid_rowconfigure(0, weight=1)

        # -- carte réglages --------------------------------------------------
        left = tk.Frame(content, bg=PANEL)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, s(10)))
        left.grid_columnconfigure(0, weight=1)
        pad = s(22)

        self._label(left, "SETUP", 9, MUTED, True).grid(row=0, column=0, sticky="w", padx=pad, pady=(pad, s(12)))
        self._label(left, "Discord Application ID").grid(row=1, column=0, sticky="w", padx=pad)
        self.client_id_entry = self._entry(left)
        self.client_id_entry.grid(row=2, column=0, sticky="ew", padx=pad, pady=(s(6), s(14)), ipady=s(7))
        self.client_id_entry.insert(0, self.config_data["client_id"])

        self._label(left, "Small image asset key").grid(row=3, column=0, sticky="w", padx=pad)
        self.asset_key_entry = self._entry(left)
        self.asset_key_entry.grid(row=4, column=0, sticky="ew", padx=pad, pady=(s(6), s(8)), ipady=s(7))
        self.asset_key_entry.insert(0, self.config_data["asset_key"])

        self._label(
            left,
            "Upload assets/app_icon.png in Discord Developer Portal → Rich Presence → Art Assets, with the same key.",
            8, MUTED, justify="left", anchor="w", wraplength=s(250),
        ).grid(row=5, column=0, sticky="w", padx=pad)

        self._check(left, "Start monitoring when the app opens", self.auto_monitor_var, self._save_settings).grid(
            row=6, column=0, sticky="w", padx=pad, pady=(s(12), 0)
        )
        if startup.is_supported():
            self._check(left, "Launch with Windows (minimized)", self.autostart_var, self._toggle_autostart).grid(
                row=7, column=0, sticky="w", padx=pad
            )

        self.start_button = FlatButton(left, "Start monitoring", self._start_monitoring, ACCENT, ACCENT_HOVER, bold=True, pady=s(10))
        self.start_button.grid(row=8, column=0, sticky="ew", padx=pad, pady=(s(14), s(8)))
        self.stop_button = FlatButton(left, "Stop", self._stop_monitoring, "#252932", "#303541", pady=s(8))
        self.stop_button.grid(row=9, column=0, sticky="ew", padx=pad)
        self.stop_button.set_enabled(False)
        FlatButton(left, "Open Roblox logs", self._open_logs, PANEL, PANEL_ALT, fg=MUTED, border="#292e38", pady=s(6)).grid(
            row=10, column=0, sticky="ew", padx=pad, pady=(s(10), pad)
        )

        # -- carte session ---------------------------------------------------
        right = tk.Frame(content, bg=BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(s(10), 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        card = tk.Frame(right, bg=PANEL)
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        self._label(card, "CURRENT SESSION", 9, MUTED, True).grid(row=0, column=0, sticky="w", padx=s(24), pady=(s(22), s(8)))

        art = tk.Frame(card, bg="#0b0d12")
        art.grid(row=1, column=0, sticky="nsew", padx=s(24), pady=(0, s(16)))
        art.grid_propagate(False)
        art.grid_columnconfigure(0, weight=1)
        art.grid_rowconfigure(0, weight=1)
        self.art_label = self._label(art, "ROBLOX\nWAITING FOR GAME", 11, "#646b78", True, justify="center", bg="#0b0d12")
        self.art_label.grid(row=0, column=0)

        self.game_name = self._label(card, "No game detected", 17, TEXT, True, anchor="w", wraplength=s(420), justify="left")
        self.game_name.grid(row=2, column=0, sticky="ew", padx=s(24))
        self.game_subtitle = self._label(card, "Launch a Roblox experience to see it here.", 9, MUTED, anchor="w")
        self.game_subtitle.grid(row=3, column=0, sticky="ew", padx=s(24), pady=(s(4), s(10)))
        self.view_button = FlatButton(card, "View game page", self._open_game, PANEL, PANEL_ALT, fg=MUTED, border="#292e38", pady=s(5))
        self.view_button.grid(row=4, column=0, sticky="w", padx=s(24), pady=(0, s(20)))
        self.view_button.set_enabled(False)

        status = tk.Frame(right, bg=PANEL)
        status.grid(row=1, column=0, sticky="ew", pady=(s(12), 0))
        status.grid_columnconfigure(0, weight=1)
        self._label(status, "ACTIVITY STATUS", 8, MUTED, True).grid(row=0, column=0, sticky="w", padx=s(20), pady=(s(14), s(3)))
        self.status_label = self._label(
            status, "Configure your Discord app, then start monitoring.", 9, TEXT, anchor="w", justify="left", wraplength=s(430)
        )
        self.status_label.grid(row=1, column=0, sticky="ew", padx=s(20), pady=(0, s(14)))

        self._label(self, "LOCAL DETECTION  ·  NO ROBLOX LOGIN REQUIRED", 8, "#555b66", True).grid(
            row=2, column=0, pady=(0, s(14))
        )

    # -- actions ------------------------------------------------------------ #
    def _set_status(self, text: str, color: str = TEXT) -> None:
        self.status_label.configure(text=text, fg=color)

    def _set_badge(self, text: str, color: str) -> None:
        self.badge.configure(text=f"●  {text}", fg=color)

    def _save_settings(self) -> None:
        self.config_data = {
            "client_id": self.client_id_entry.get().strip(),
            "asset_key": self.asset_key_entry.get().strip() or "rbx_presence",
            "auto_monitor": bool(self.auto_monitor_var.get()),
        }
        try:
            save_config(self.config_data)
        except OSError as error:
            self._set_status(f"Could not save settings: {error}", BAD)

    def _toggle_autostart(self) -> None:
        try:
            startup.set_enabled(bool(self.autostart_var.get()))
        except OSError as error:
            self.autostart_var.set(startup.is_enabled())
            self._set_status(f"Could not change Windows startup: {error}", BAD)

    def _start_monitoring(self) -> None:
        if self.monitoring:
            return
        self._save_settings()
        client_id = self.config_data["client_id"]
        if not client_id.isdigit():
            self._set_status("Enter a valid numeric Discord Application ID first.", BAD)
            return

        self.controller.start(client_id, self.config_data["asset_key"])
        self.monitoring = True
        self.start_button.set_enabled(False)
        self.stop_button.set_enabled(True)
        self._set_badge("MONITORING", "#ff7379")
        self._set_status("Monitoring Roblox and waiting for a game…")

    def _stop_monitoring(self) -> None:
        self.controller.stop()
        self.monitoring = False
        # vide les événements restants pour ne pas réécrire l'état après l'arrêt
        while not self.events.empty():
            try:
                self.events.get_nowait()
            except queue.Empty:
                break
        self.start_button.set_enabled(True)
        self.stop_button.set_enabled(False)
        self._set_badge("DISCONNECTED", "#c4c7cf")
        self._set_status("Monitoring stopped.", MUTED)
        self._show_game(None)

    def _show_game(self, game) -> None:
        if game:
            self.game_url = game.game_url
            self.game_name.configure(text=game.name)
            self.game_subtitle.configure(text=f"Place ID  {game.place_id}   ·   Universe ID  {game.universe_id}")
            self.art_label.configure(text="NOW PLAYING", fg=ACCENT)
            self.view_button.set_enabled(True)
        else:
            self.game_url = None
            self.game_name.configure(text="No game detected")
            self.game_subtitle.configure(text="Launch a Roblox experience to see it here.")
            self.art_label.configure(text="ROBLOX\nWAITING FOR GAME", fg="#646b78")
            self.view_button.set_enabled(False)

    def _poll_events(self) -> None:
        # Fenêtre minimisée : on vide quand même la file (peu coûteux).
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if not self.monitoring:
                continue

            color = BAD if event.kind == "error" else TEXT
            self._set_status(event.message, color)

            if event.kind == "playing" and event.game:
                self._set_badge("LIVE", OK)
                self._show_game(event.game)
            elif event.kind == "idle":
                self._set_badge("ROBLOX OFF", "#c4c7cf")
                self._show_game(None)
            elif event.kind in ("detecting", "loading"):
                self._set_badge("DETECTING", WARN)
            elif event.kind == "error":
                self._set_badge("ERROR", BAD)

        self.after(500, self._poll_events)

    def _open_game(self) -> None:
        if self.game_url:
            webbrowser.open(self.game_url)

    def _open_logs(self) -> None:
        for directory in get_log_directories():
            if directory.exists():
                if hasattr(os, "startfile"):
                    os.startfile(directory)  # type: ignore[attr-defined]
                else:
                    webbrowser.open(directory.as_uri())
                return
        self._set_status("Roblox log folder was not found yet.", BAD)

    def _on_close(self) -> None:
        self.controller.stop()
        self.destroy()
