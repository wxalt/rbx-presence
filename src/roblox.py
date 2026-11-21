"""Détection de la session Roblox (logs locaux) + infos publiques de l'expérience.

Conçu pour une consommation minimale :
  * les logs sont lus de façon incrémentale (seuls les octets nouveaux sont lus) ;
  * aucune dépendance lourde (urllib de la stdlib à la place de requests) ;
  * les réponses de l'API sont mises en cache.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

USER_AGENT = "RBXPresence/2.0 (Windows; Discord Rich Presence)"
REQUEST_TIMEOUT = 6
MAX_RESPONSE_BYTES = 1_000_000
CACHE_SIZE = 16

PROCESS_NAMES = frozenset(
    {"robloxplayerbeta.exe", "robloxplayer.exe", "windows10universal.exe"}
)


class RobloxError(RuntimeError):
    """Erreur réseau / API Roblox (message affichable à l'utilisateur)."""


@dataclass(frozen=True)
class GameSession:
    place_id: int
    universe_id: int | None


@dataclass(frozen=True)
class GameInfo:
    name: str
    place_id: int
    universe_id: int
    thumbnail_url: str | None
    game_url: str


# --------------------------------------------------------------------------- #
# Processus
# --------------------------------------------------------------------------- #
def is_roblox_running() -> bool:
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info.get("name") or "").lower() in PROCESS_NAMES:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False


# --------------------------------------------------------------------------- #
# Logs
# --------------------------------------------------------------------------- #
def get_log_directories() -> list[Path]:
    local_app_data = Path(os.getenv("LOCALAPPDATA", Path.home()))
    return [
        local_app_data / "Roblox" / "logs",
        local_app_data
        / "Packages"
        / "ROBLOXCorporation.ROBLOX_55nm5eh3cm0pr"
        / "LocalState"
        / "logs",
    ]


_MODERN = re.compile(r"placeId=(\d+).*?universeId=(\d+)", re.IGNORECASE)
_LEGACY = re.compile(r"universeid\s*:\s*(\d+).*?placeid\s*:\s*(\d+)", re.IGNORECASE)
_JOINING = re.compile(r"! Joining game .*? place (\d+)", re.IGNORECASE)


def _parse_line(line: bytes) -> GameSession | None:
    low = line.lower()
    if b"gamejoinaggregator" in low:
        match = _MODERN.search(line.decode("utf-8", "ignore"))
        if match:
            return GameSession(int(match.group(1)), int(match.group(2)))
    if b"universeid" in low and b"placeid" in low:
        match = _LEGACY.search(line.decode("utf-8", "ignore"))
        if match:
            return GameSession(int(match.group(2)), int(match.group(1)))
    if b"joining game" in low:
        match = _JOINING.search(line.decode("utf-8", "ignore"))
        if match:
            return GameSession(int(match.group(1)), None)
    return None


def _newest_log() -> Path | None:
    players: list[tuple[float, str]] = []
    others: list[tuple[float, str]] = []

    for directory in get_log_directories():
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    name = entry.name.lower()
                    if not name.endswith((".log", ".txt")):
                        continue
                    try:
                        item = (entry.stat().st_mtime, entry.path)
                    except OSError:
                        continue
                    (players if "_player_" in name else others).append(item)
        except OSError:
            continue

    pool = players or others
    return Path(max(pool)[1]) if pool else None


class LogWatcher:
    """Suit le log Roblox le plus récent en ne lisant que les nouveaux octets."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._path: Path | None = None
        self._offset = 0
        self._session: GameSession | None = None

    def poll(self) -> GameSession | None:
        path = _newest_log()
        if path is None:
            self.reset()
            return None

        if path != self._path:
            self._path, self._offset, self._session = path, 0, None

        try:
            size = path.stat().st_size
            if size < self._offset:  # log tronqué / recréé
                self._offset, self._session = 0, None
            if size == self._offset:
                return self._session

            with path.open("rb") as file:
                file.seek(self._offset)
                for line in file:
                    if not line.endswith(b"\n"):
                        break  # ligne encore en cours d'écriture
                    self._offset += len(line)
                    found = _parse_line(line)
                    if found:
                        self._session = self._merge(found)
        except OSError:
            pass

        return self._session

    def _merge(self, found: GameSession) -> GameSession:
        previous = self._session
        if found.universe_id is None and previous and previous.place_id == found.place_id:
            return previous
        return found


# --------------------------------------------------------------------------- #
# API publique Roblox
# --------------------------------------------------------------------------- #
def _request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read(MAX_RESPONSE_BYTES))
    except urllib.error.HTTPError as error:
        raise RobloxError(f"Roblox API error ({error.code})") from error
    except (OSError, ValueError) as error:  # URLError, timeout, JSON invalide
        raise RobloxError("Cannot reach Roblox (check your connection)") from error

    if not isinstance(payload, dict):
        raise RobloxError("Unexpected response from Roblox")
    return payload


def resolve_universe_id(place_id: int) -> int | None:
    try:
        payload = _request_json(
            f"https://apis.roblox.com/universes/v1/places/{place_id}/universe"
        )
        universe_id = payload.get("universeId")
        return int(universe_id) if universe_id else None
    except (RobloxError, TypeError, ValueError):
        return None


def get_game_thumbnail(universe_id: int) -> str | None:
    endpoints = (
        "https://thumbnails.roblox.com/v1/games/multiget/thumbnails"
        f"?universeIds={universe_id}&countPerUniverse=1&defaults=true"
        "&size=768x432&format=Png&isCircular=false",
        "https://thumbnails.roblox.com/v1/games/icons"
        f"?universeIds={universe_id}&size=512x512&format=Png&isCircular=false",
    )
    for url in endpoints:
        try:
            data = _request_json(url).get("data") or []
            if not data:
                continue
            first = data[0]
            if isinstance(first.get("thumbnails"), list) and first["thumbnails"]:
                image_url = first["thumbnails"][0].get("imageUrl")
            else:
                image_url = first.get("imageUrl")
            if image_url:
                return str(image_url)
        except (RobloxError, AttributeError, KeyError, TypeError):
            continue
    return None


_cache: OrderedDict[int, GameInfo] = OrderedDict()


def get_game_info(session: GameSession) -> GameInfo:
    cached = _cache.get(session.place_id)
    if cached:
        _cache.move_to_end(session.place_id)
        return cached

    universe_id = session.universe_id or resolve_universe_id(session.place_id)
    if not universe_id:
        raise RobloxError("Could not resolve this Roblox experience")

    games = _request_json(
        f"https://games.roblox.com/v1/games?universeIds={universe_id}"
    ).get("data") or []
    if not games:
        raise RobloxError("Roblox did not return this game's information")

    info = GameInfo(
        name=str(games[0].get("name") or "Roblox Experience"),
        place_id=session.place_id,
        universe_id=universe_id,
        thumbnail_url=get_game_thumbnail(universe_id),
        game_url=f"https://www.roblox.com/games/{session.place_id}",
    )
    _cache[session.place_id] = info
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return info
