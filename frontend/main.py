import curses
import locale
import sys
import time
import traceback

from clock import (
    PlaybackClock,
    clean_metadata,
    fetch_auto_lyrics,
    find_lyric_index,
    get_lyrics,
)
from player import get_metadata, get_position, get_status

POLL_INTERVAL = 100
METADATA_POLL_SEC = 1.5


def prompt(stdscr, header, label):
    curses.flushinp()
    stdscr.timeout(-1)
    curses.curs_set(1)

    height, width = stdscr.getmaxyx()
    y = height // 2
    buf = []

    while True:
        stdscr.erase()
        try:
            stdscr.addnstr(y - 3, 2, "Buscar letra (Enter vacío para cancelar)", width - 4)
            if header:
                stdscr.addnstr(y - 1, 2, header, width - 4)
            text_line = label + "".join(buf)
            stdscr.addnstr(y, 2, text_line, width - 4)
        except curses.error:
            pass
        stdscr.refresh()

        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue

        if ch in ("\n", "\r", curses.KEY_ENTER):
            break
        elif ch in (curses.KEY_BACKSPACE, "\b", "\x7f"):
            if buf:
                buf.pop()
        elif ch == "\x1b":
            buf = []
            break
        elif isinstance(ch, str) and ch.isprintable():
            buf.append(ch)

    curses.curs_set(0)
    stdscr.timeout(POLL_INTERVAL)
    return "".join(buf).strip()


def show_message(stdscr, message, wait=False):
    height, width = stdscr.getmaxyx()
    stdscr.erase()
    try:
        stdscr.addnstr(height // 2, 2, message, width - 4)
    except curses.error:
        pass
    stdscr.refresh()

    if wait:
        curses.flushinp()
        stdscr.timeout(-1)
        stdscr.getch()
        stdscr.timeout(POLL_INTERVAL)


def search_song(stdscr):
    while True:
        title = prompt(stdscr, "", "Canción: ")
        if not title:
            return None

        artist = prompt(stdscr, f"Canción: {title}", "Artista: ")
        show_message(stdscr, f"Buscando: {title} {artist}...")
        data, error = get_lyrics(title, artist)

        if data is not None:
            return data

        show_message(stdscr, f"{error} (pulsa una tecla)", wait=True)


def draw_bar(stdscr, position, duration, width, y):
    if duration <= 0:
        return
    bar_width = max(10, width - 4)
    ratio = min(max(position / duration, 0.0), 1.0)
    filled = int(bar_width * ratio)
    bar = "━" * filled + "─" * (bar_width - filled)
    pct = f"{ratio * 100:5.1f}%"
    try:
        stdscr.addnstr(y - 1, max(2, width - len(pct) - 2), pct, len(pct))
        stdscr.addnstr(y, 2, bar, width - 4)
    except curses.error:
        pass


def draw_lyrics(stdscr, data, clock, status, auto_mode, status_note=""):
    height, width = stdscr.getmaxyx()
    stdscr.erase()

    position = clock.position()
    duration = data.get("duration", 0)
    if duration > 0:
        position = min(position, duration)

    mode_tag = "[AUTO]" if auto_mode else "[MANUAL]"
    header = f"{mode_tag} {data['artist']} - {data['title']}"
    try:
        stdscr.addnstr(0, 0, header.center(width), width - 1, curses.A_BOLD)
    except curses.error:
        pass

    lyrics = data.get("lyrics", [])

    if not lyrics:
        msg = status_note or "No hay letras sincronizadas para esta pista"
        try:
            stdscr.addnstr(height // 2, 2, msg, width - 4)
        except curses.error:
            pass
    else:
        current_idx = find_lyric_index(lyrics, position)
        center_y = height // 2
        visible_radius = max(1, (height - 6) // 2)

        for offset_line in range(-visible_radius, visible_radius + 1):
            idx = current_idx + offset_line
            y = center_y + offset_line
            if y < 2 or y >= height - 4:
                continue
            if 0 <= idx < len(lyrics):
                text = lyrics[idx]["text"]
                attr = curses.A_BOLD | curses.A_REVERSE if offset_line == 0 else curses.A_DIM
                try:
                    stdscr.addnstr(y, 2, text.center(width - 4), width - 4, attr)
                except curses.error:
                    pass

    draw_bar(stdscr, position, duration, width, height - 3)

    offset_str = f"{clock.offset:+.1f}s"
    info_line = (
        f"Estado: {status or 'Sin reproductor'} | {position:5.1f}s | "
        f"Sync: {offset_str} (+/- ajustar, 0 reset)"
    )
    controls_line = "S: buscar manual | A: modo auto | R: reiniciar a 0 | Q: salir"

    try:
        stdscr.addnstr(height - 2, 2, info_line, width - 4)
        stdscr.addnstr(height - 1, 2, controls_line, width - 4, curses.A_DIM)
    except curses.error:
        pass

    stdscr.refresh()


def interface(stdscr, initial_data):
    curses.curs_set(0)
    stdscr.timeout(POLL_INTERVAL)

    clock = PlaybackClock()
    data = initial_data
    auto_mode = initial_data is None
    last_track = None
    last_meta_check = 0.0
    status_note = ""

    if auto_mode:
        meta = get_metadata()
        if meta.get("title"):
            raw_title = meta["title"]
            raw_artist = meta.get("artist") or ""
            last_track = (raw_title, raw_artist)
            clean_t, clean_a = clean_metadata(raw_title, raw_artist)
            show_message(stdscr, f"Detectado: {clean_a} - {clean_t}...")
            fetched, err, _, _ = fetch_auto_lyrics(raw_title, raw_artist)
            if fetched:
                data = fetched
                clock.on_track_change(get_status(), get_position())
            else:
                data = {
                    "title": clean_t,
                    "artist": clean_a,
                    "duration": 0,
                    "lyrics": []
                }
                status_note = f"Sin letra en LRCLIB ({err})"
        else:
            auto_mode = False
            data = search_song(stdscr)
            if data is None:
                return

    while True:
        now = time.time()
        status = get_status()
        player_pos = get_position()

        if auto_mode and (now - last_meta_check >= METADATA_POLL_SEC):
            last_meta_check = now
            meta = get_metadata()
            raw_title = meta.get("title")
            raw_artist = meta.get("artist") or ""
            current_track = (raw_title, raw_artist)

            if raw_title and current_track != last_track:
                last_track = current_track
                status_note = ""
                clean_t, clean_a = clean_metadata(raw_title, raw_artist)

                show_message(stdscr, f"Cambiando a: {clean_a} - {clean_t}...")
                fetched, err, _, _ = fetch_auto_lyrics(raw_title, raw_artist)
                if fetched:
                    data = fetched
                else:
                    data = {
                        "title": clean_t,
                        "artist": clean_a,
                        "duration": 0,
                        "lyrics": []
                    }
                    status_note = f"Sin letra en LRCLIB ({err})"
                clock.on_track_change(status, player_pos)

        clock.sync_with_player(status, player_pos)
        draw_lyrics(stdscr, data, clock, status, auto_mode, status_note)

        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            break
        elif key in (ord("+"), ord("=")):
            clock.adjust_offset(0.2)
        elif key in (ord("-"), ord("_")):
            clock.adjust_offset(-0.2)
        elif key == ord("0"):
            clock.reset_offset()
        elif key in (ord("r"), ord("R")):
            clock.reset_to_zero(status)
        elif key in (ord("a"), ord("A")):
            auto_mode = True
            last_track = None
            last_meta_check = 0.0
            clock.reset_offset()
        elif key in (ord("s"), ord("S")):
            new_data = search_song(stdscr)
            if new_data is not None:
                auto_mode = False
                data = new_data
                status_note = ""
                clock.reset_to_zero(status)
                clock.reset_offset()


def main():
    locale.setlocale(locale.LC_ALL, "")

    data = None
    if len(sys.argv) > 1:
        title = sys.argv[1]
        artist = sys.argv[2] if len(sys.argv) > 2 else ""
        data, error = get_lyrics(title, artist)
        if data is None:
            print(f"[lyrics-ui] {error}", file=sys.stderr)
            return

    try:
        curses.wrapper(interface, data)
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()

