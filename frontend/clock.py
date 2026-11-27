import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINARY = ROOT / "lyrics-cli"


def clean_metadata(title, artist):
    artist = re.sub(r"(?i)(vevo|official|\s*-\s*topic)$", "", artist or "").strip()
    title = re.sub(r"[\(\[].*?[\)\]]", "", title or "").strip()
    title = re.sub(r"(?i)\b(official\s*(music\s*)?video|lyric\s*video|audio|hd|4k)\b", "", title).strip()

    if " - " in title:
        parts = title.split(" - ", 1)
        artist = parts[0].strip()
        title = parts[1].strip()

    return title, artist


class PlaybackClock:
    def __init__(self):
        self.status = None
        self.started_at = None
        self.paused_position = 0.0
        self.offset = 0.0
        self.follow_player_pos = True
        self.last_player_pos = None

    def sync_with_player(self, status, player_pos):
        now = time.time()
        current = self.raw_position()

        # 1. Principal: verificar si player_pos realmente está cambiando respecto al ciclo anterior
        pos_changed = (
            player_pos is not None
            and self.last_player_pos is not None
            and abs(player_pos - self.last_player_pos) > 0.05
        )
        if player_pos is not None:
            self.last_player_pos = player_pos

        # 2. Fallback: ignorar reportes congelados en 0.0 del navegador cuando la pista ya avanzó
        is_stuck_zero = (
            player_pos is not None
            and player_pos <= 0.1
            and current > 1.5
            and self.status == "Playing"
        )

        # Solo resincronizar si el reproductor reportó un cambio real de posición
        use_player_pos = (
            self.follow_player_pos
            and player_pos is not None
            and pos_changed
            and not is_stuck_zero
        )

        if use_player_pos:
            if abs(player_pos - current) > 0.8 or self.status != status:
                self.paused_position = player_pos
                self.started_at = now - player_pos if status == "Playing" else None
                self.status = status
                return

        if status != self.status:
            if status == "Playing":
                if self.paused_position == 0.0 and player_pos is not None and player_pos > 0.1:
                    self.paused_position = player_pos
                self.started_at = now - self.paused_position
            elif status == "Paused":
                if self.started_at is not None:
                    self.paused_position = now - self.started_at
            elif status == "Stopped":
                self.started_at = None
                self.paused_position = 0.0
                self.last_player_pos = None
            self.status = status

    def on_track_change(self, status, player_pos=None):
        self.follow_player_pos = True
        self.offset = 0.0
        self.last_player_pos = player_pos
        initial_pos = player_pos if (player_pos is not None and player_pos > 0.1) else 0.0
        self.paused_position = initial_pos
        self.started_at = time.time() - initial_pos if status == "Playing" else None
        self.status = status

    def reset_to_zero(self, status):
        self.follow_player_pos = False
        self.status = status
        self.paused_position = 0.0
        self.last_player_pos = None
        self.started_at = time.time() if status == "Playing" else None

    def adjust_offset(self, delta):
        self.offset = round(self.offset + delta, 2)

    def reset_offset(self):
        self.offset = 0.0
        self.follow_player_pos = True

    def raw_position(self):
        if self.status == "Playing" and self.started_at is not None:
            return time.time() - self.started_at
        return self.paused_position

    def position(self):
        return max(0.0, self.raw_position() + self.offset)


def get_lyrics(title, artist):
    cmd = [str(BINARY), str(title), str(artist)] if BINARY.exists() else ["go", "run", ".", str(title), str(artist)]
    try:
        process = subprocess.run(
            cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
    except FileNotFoundError:
        return None, "No se encontró Go ni el binario lyrics-cli"

    if process.returncode != 0:
        lines = [l for l in process.stderr.splitlines() if l.strip()]
        reason = lines[-1] if lines else "Error ejecutando backend Go"
        return None, reason

    try:
        return json.loads(process.stdout), None
    except json.JSONDecodeError as error:
        return None, f"Error decodificando JSON: {error}"


def fetch_auto_lyrics(raw_title, raw_artist):
    clean_t, clean_a = clean_metadata(raw_title, raw_artist)
    fetched, err = get_lyrics(clean_t, clean_a)
    if fetched is None and clean_a:
        fetched, err = get_lyrics(clean_t, "")
    return fetched, err, clean_t, clean_a


def find_lyric_index(lyrics, position):
    result = -1
    for i, line in enumerate(lyrics):
        if line["time"] <= position:
            result = i
        else:
            break
    return result

