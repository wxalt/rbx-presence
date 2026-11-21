from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any

from pypresence import Presence
from pypresence.exceptions import DiscordNotFound, InvalidID

from .roblox import (
    GameInfo,
    LogWatcher,
    RobloxError,
    get_game_info,
    is_roblox_running,
)

POLL_SECONDS = 5          # cadence de la boucle (très léger : un stat() sur le log)
RETRY_SECONDS = 15        # délai après une erreur réseau / Discord
REFRESH_SECONDS = 45      # ré-envoi de la présence (détecte un Discord redémarré)


@dataclass
class ControllerEvent:
    kind: str  # idle | detecting | loading | playing | error
    message: str
    game: GameInfo | None = None


class PresenceController:
    def __init__(self, events: queue.Queue[ControllerEvent]) -> None:
        self.events = events
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.client_id = ""
        self.asset_key = "rbx_presence"
        self.pipe: int | None = None
        self._last_event: tuple[str, str] | None = None

    # -- cycle de vie ------------------------------------------------------- #
    def start(self, client_id: str, asset_key: str, pipe: int | None = None) -> None:
        self.stop()
        self.client_id = client_id.strip()
        self.asset_key = asset_key.strip()
        self.pipe = pipe
        self.stop_event = threading.Event()
        self._last_event = None
        self.thread = threading.Thread(
            target=self._run, args=(self.stop_event,), daemon=True, name="presence"
        )
        self.thread.start()

    def stop(self) -> None:
        if self.thread and self.thread.is_alive():
            self.stop_event.set()
            self.thread.join(timeout=8)
        self.thread = None

    def _emit(self, kind: str, message: str, game: GameInfo | None = None) -> None:
        if self._last_event == (kind, message):
            return
        self._last_event = (kind, message)
        self.events.put(ControllerEvent(kind, message, game))

    # -- Discord ------------------------------------------------------------ #
    def _connect(self) -> Presence:
        rpc = Presence(self.client_id, pipe=self.pipe)
        try:
            rpc.connect()
        except BaseException:
            self._close(rpc, clear=False)
            raise
        return rpc

    @staticmethod
    def _close(rpc: Presence | None, clear: bool = True) -> None:
        if rpc is None:
            return
        try:
            if clear:
                rpc.clear()
        except Exception:
            pass
        try:
            rpc.close()
        except Exception:
            pass

    def _activity(self, game: GameInfo, started: int) -> dict[str, Any]:
        activity: dict[str, Any] = {
            "name": "Roblox",
            "details": game.name[:128],
            "state": "In game",
            "start": started,
            "large_text": game.name[:128],
            "large_url": game.game_url,
            "buttons": [{"label": "View Game", "url": game.game_url}],
        }
        if game.thumbnail_url:
            activity["large_image"] = game.thumbnail_url
        if self.asset_key:
            activity["small_image"] = self.asset_key
            activity["small_text"] = "RBX Presence"
        return activity

    # -- boucle principale -------------------------------------------------- #
    def _run(self, stop: threading.Event) -> None:
        watcher = LogWatcher()
        rpc: Presence | None = None
        game: GameInfo | None = None
        place_id: int | None = None
        started = int(time.time())
        last_push = 0.0
        retry_at = 0.0

        try:
            while not stop.is_set():
                now = time.monotonic()
                try:
                    if not is_roblox_running():
                        self._close(rpc)
                        rpc, game, place_id, last_push = None, None, None, 0.0
                        watcher.reset()
                        self._emit("idle", "Roblox is not running")

                    elif now >= retry_at:
                        session = watcher.poll()
                        if session is None:
                            self._emit("detecting", "Roblox detected · Waiting for game data")
                        else:
                            if session.place_id != place_id:
                                self._emit("loading", "Loading experience information")
                                game = get_game_info(session)
                                place_id = session.place_id
                                started = int(time.time())
                                last_push = 0.0  # force l'envoi

                            if game and (rpc is None or now - last_push >= REFRESH_SECONDS):
                                if rpc is None:
                                    rpc = self._connect()
                                rpc.update(**self._activity(game, started))
                                last_push = now
                                self._emit("playing", game.name, game)

                except DiscordNotFound:
                    self._fail(rpc, "Discord desktop is not open")
                    rpc, retry_at = None, now + RETRY_SECONDS
                except InvalidID:
                    self._fail(rpc, "Invalid Discord Application ID")
                    rpc, retry_at = None, now + RETRY_SECONDS * 2
                except RobloxError as error:
                    self._emit("error", str(error))
                    retry_at = now + RETRY_SECONDS
                except Exception as error:  # pipe Discord cassé, etc.
                    self._fail(rpc, (str(error) or type(error).__name__)[:180])
                    rpc, retry_at = None, now + RETRY_SECONDS

                stop.wait(POLL_SECONDS)
        finally:
            self._close(rpc)

    def _fail(self, rpc: Presence | None, message: str) -> None:
        self._close(rpc, clear=False)
        self._emit("error", message)
