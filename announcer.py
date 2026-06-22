import discord
import urllib.parse
import io
import logging

log = logging.getLogger("announcer")

# Farben je Medientyp
COLOR_MOVIE = 0xE5A00D    # Plex-Gold
COLOR_SHOW = 0x1DB954     # Grün
COLOR_EPISODE = 0x5865F2  # Discord-Blau
COLOR_MUSIC = 0xEB459E    # Pink

# Emojis
EMOJI_MOVIE = "🎬"
EMOJI_SHOW = "📺"
EMOJI_EPISODE = "▶️"
EMOJI_MUSIC = "🎵"
EMOJI_STAR = "⭐"
EMOJI_CLOCK = "⏱️"
EMOJI_CALENDAR = "📅"
EMOJI_GENRE = "🎭"
EMOJI_SEASON = "📂"
EMOJI_EPISODE_NR = "🎞️"


def _format_duration(ms: int) -> str:
    """Millisekunden in h:mm:ss umwandeln"""
    total_sec = ms // 1000
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d} Std."
    return f"{m}:{s:02d} Min."


def _format_rating(rating) -> str:
    try:
        return f"{float(rating):.1f} / 10"
    except (ValueError, TypeError):
        return str(rating)


def _truncate(text: str, max_len: int = 350) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


class Announcer:
    def __init__(self, urls: list, plex_url: str, plex_token: str = None) -> None:
        self.plex_url = plex_url.rstrip("/")
        self.plex_token = plex_token
        self.webhooks = []

        for url in urls:
            log.debug(f"Webhook erstellt für: {url}")
            wh_id, token = self._parse_url(url)
            try:
                wh_id_int = int(wh_id)
            except ValueError:
                log.error(f"Ungültige Webhook-ID in URL: {url}")
                continue
            webhook = discord.SyncWebhook.partial(wh_id_int, token)
            self.webhooks.append(webhook)

    def _parse_url(self, url: str):
        cleaned = (
            url.replace("https://discord.com/api/webhooks/", "")
            .replace("https://discordapp.com/api/webhooks/", "")
        )
        parts = cleaned.split("/")
        return parts[0], parts[1]

    def _plex_link(self, key: str) -> str:
        key_encoded = urllib.parse.quote_plus(key.replace("/children", ""))
        return f"{self.plex_url}/details?key={key_encoded}"

    def _send(self, embed: discord.Embed, thumbnail_bytes: bytes):
        """Embed an alle Webhooks senden – Poster als großes Bild"""
        file = discord.File(io.BytesIO(thumbnail_bytes), filename="poster.jpg")
        embed.set_image(url="attachment://poster.jpg")

        for webhook in self.webhooks:
            try:
                # Datei-Objekt kann nur einmal gelesen werden → neu erstellen
                f = discord.File(io.BytesIO(thumbnail_bytes), filename="poster.jpg")
                webhook.send(embed=embed, file=f)
            except Exception as e:
                log.error(f"Fehler beim Senden an Webhook: {e}")

    # ------------------------------------------------------------------ #
    #  FILM                                                                #
    # ------------------------------------------------------------------ #
    def announce_movie(self, meta: dict, thumbnail: bytes):
        log.debug("Film-Ankündigung wird erstellt")

        embed = discord.Embed(color=COLOR_MOVIE)
        embed.set_author(name=f"{EMOJI_MOVIE}  Neuer Film in der Bibliothek")

        title = meta.get("title", "Unbekannt")
        year = meta.get("year", "")
        embed.title = f"{title} ({year})" if year else title
        embed.url = self._plex_link(meta.get("key", ""))

        if meta.get("summary"):
            embed.description = _truncate(meta["summary"])

        # Felder
        if meta.get("duration"):
            embed.add_field(
                name=f"{EMOJI_CLOCK} Laufzeit",
                value=_format_duration(meta["duration"]),
                inline=True,
            )
        if meta.get("rating"):
            embed.add_field(
                name=f"{EMOJI_STAR} Bewertung",
                value=_format_rating(meta["rating"]),
                inline=True,
            )
        if meta.get("audienceRating"):
            embed.add_field(
                name=f"{EMOJI_STAR} Zuschauer",
                value=_format_rating(meta["audienceRating"]),
                inline=True,
            )
        genres = [g["tag"] for g in meta.get("Genre", []) if "tag" in g]
        if genres:
            embed.add_field(
                name=f"{EMOJI_GENRE} Genre",
                value=" · ".join(genres[:4]),
                inline=False,
            )

        directors = [d["tag"] for d in meta.get("Director", []) if "tag" in d]
        if directors:
            embed.add_field(
                name="🎥 Regie",
                value=", ".join(directors[:3]),
                inline=True,
            )

        embed.set_footer(text="Plex · Neues Medium verfügbar")
        self._send(embed, thumbnail)

    # ------------------------------------------------------------------ #
    #  SERIE (komplett neu)                                                #
    # ------------------------------------------------------------------ #
    def announce_show(self, meta: dict, thumbnail: bytes):
        log.debug("Serien-Ankündigung wird erstellt")

        embed = discord.Embed(color=COLOR_SHOW)
        embed.set_author(name=f"{EMOJI_SHOW}  Neue Serie in der Bibliothek")

        title = meta.get("title", "Unbekannt")
        year = meta.get("year", "")
        embed.title = f"{title} ({year})" if year else title
        embed.url = self._plex_link(meta.get("key", ""))

        if meta.get("summary"):
            embed.description = _truncate(meta["summary"])

        if meta.get("childCount"):
            embed.add_field(
                name=f"{EMOJI_SEASON} Staffeln",
                value=str(meta["childCount"]),
                inline=True,
            )
        if meta.get("leafCount"):
            embed.add_field(
                name=f"{EMOJI_EPISODE_NR} Episoden",
                value=str(meta["leafCount"]),
                inline=True,
            )
        if meta.get("rating"):
            embed.add_field(
                name=f"{EMOJI_STAR} Bewertung",
                value=_format_rating(meta["rating"]),
                inline=True,
            )

        genres = [g["tag"] for g in meta.get("Genre", []) if "tag" in g]
        if genres:
            embed.add_field(
                name=f"{EMOJI_GENRE} Genre",
                value=" · ".join(genres[:4]),
                inline=False,
            )

        embed.set_footer(text="Plex · Neues Medium verfügbar")
        self._send(embed, thumbnail)

    # ------------------------------------------------------------------ #
    #  EPISODE                                                             #
    # ------------------------------------------------------------------ #
    def announce_episode(self, meta: dict, thumbnail: bytes):
        log.debug("Episoden-Ankündigung wird erstellt")

        embed = discord.Embed(color=COLOR_EPISODE)

        season = meta.get("parentIndex")
        episode = meta.get("index")

        # Neue Staffel oder neue Episode?
        if season and episode == 1:
            embed.set_author(
                name=f"{EMOJI_SHOW}  Neue Staffel verfügbar"
            )
        else:
            embed.set_author(
                name=f"{EMOJI_EPISODE}  Neue Episode verfügbar"
            )

        show_title = meta.get("grandparentTitle", "Unbekannte Serie")
        ep_title = meta.get("title", "")

        if season and episode:
            ep_label = f"S{int(season):02d}E{int(episode):02d}"
            embed.title = f"{show_title} · {ep_label}"
            if ep_title:
                embed.title += f" – {ep_title}"
        else:
            embed.title = f"{show_title}" + (f": {ep_title}" if ep_title else "")

        embed.url = self._plex_link(meta.get("key", ""))

        if meta.get("summary"):
            embed.description = _truncate(meta["summary"])

        if season:
            embed.add_field(
                name=f"{EMOJI_SEASON} Staffel",
                value=str(season),
                inline=True,
            )
        if episode:
            embed.add_field(
                name=f"{EMOJI_EPISODE_NR} Episode",
                value=str(episode),
                inline=True,
            )
        if meta.get("duration"):
            embed.add_field(
                name=f"{EMOJI_CLOCK} Laufzeit",
                value=_format_duration(meta["duration"]),
                inline=True,
            )
        if meta.get("rating"):
            embed.add_field(
                name=f"{EMOJI_STAR} Bewertung",
                value=_format_rating(meta["rating"]),
                inline=True,
            )

        embed.set_footer(text="Plex · Neues Medium verfügbar")
        self._send(embed, thumbnail)

    # ------------------------------------------------------------------ #
    #  MUSIK                                                               #
    # ------------------------------------------------------------------ #
    def announce_track(self, meta: dict, thumbnail: bytes):
        log.debug("Musik-Ankündigung wird erstellt")

        embed = discord.Embed(color=COLOR_MUSIC)
        embed.set_author(name=f"{EMOJI_MUSIC}  Neuer Titel in der Bibliothek")

        artist = meta.get("grandparentTitle", "")
        album = meta.get("parentTitle", "")
        title = meta.get("title", "Unbekannt")

        embed.title = title
        if artist:
            embed.add_field(name="🎤 Künstler", value=artist, inline=True)
        if album:
            embed.add_field(name="💿 Album", value=album, inline=True)
        if meta.get("duration"):
            embed.add_field(
                name=f"{EMOJI_CLOCK} Dauer",
                value=_format_duration(meta["duration"]),
                inline=True,
            )

        embed.set_footer(text="Plex · Neues Medium verfügbar")
        self._send(embed, thumbnail)
