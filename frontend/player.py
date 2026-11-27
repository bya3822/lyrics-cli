
import subprocess


def get_playerctl(args):
    try:
        result = subprocess.run(
            ["playerctl", *args],
            capture_output=True,
            text=True,
            timeout=2
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_status():
    return get_playerctl(["status"])


def get_position():
    position = get_playerctl(["position"])

    if position is None:
        return None

    try:
        return float(position)
    except ValueError:
        return None


def get_metadata():
    title = get_playerctl(["metadata", "title"])
    artist = get_playerctl(["metadata", "artist"])

    return {
        "title": title,
        "artist": artist
    }

