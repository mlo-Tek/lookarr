import os
import logging
from aiohttp import web, hdrs
from config import Config, ConfigError
from announcer import Announcer
from security import SecurityCheck

log = logging.getLogger("main")


async def handle(request):
    """Eingehende Plex-Webhook-Anfragen verarbeiten"""
    log.info("Eingehende Anfrage")

    # === Sicherheitsprüfungen vor dem Body-Lesen ===
    pre_check = security.run_pre_checks(request)
    if pre_check is not None:
        return pre_check

    # === Body lesen ===
    try:
        reader = await request.multipart()
        metadata = None
        thumbnail = None

        while True:
            part = await reader.next()
            if part is None:
                break
            if part.headers.get(hdrs.CONTENT_TYPE) == "application/json":
                metadata = await part.json()
                continue
            thumbnail = await part.read(decode=False)

    except Exception as e:
        log.info(f"Anfrage abgelehnt: Fehler beim Lesen der Anfrage ({e})")
        return web.Response(status=400)

    # === Payload-Validierung ===
    if not security.validate_payload(metadata):
        return web.Response(status=400, text="Invalid payload")

    event = metadata["event"]

    if event == "library.new":
        try:
            handle_library_new(metadata["Metadata"], thumbnail)
        except Exception as e:
            log.error("Fehler beim Verarbeiten von library.new")
            log.exception(e)
            return web.Response(status=500)
    else:
        log.info(f"Event ignoriert: {event}")

    return web.Response()


def handle_library_new(metadata, thumbnail):
    """Medientyp bestimmen und passenden Handler aufrufen"""
    log.debug(metadata)

    library = metadata.get("librarySectionTitle", "")
    if ALLOWED_LIBRARIES:
        if library not in ALLOWED_LIBRARIES:
            log.info(f"Bibliothek ignoriert: {library}")
            return

    ptype = metadata.get("type")

    if ptype == "movie":
        log.info("Neuer Film wird angekündigt.")
        announcer.announce_movie(metadata, thumbnail)
    elif ptype == "show":
        log.info("Neue Serie wird angekündigt.")
        announcer.announce_show(metadata, thumbnail)
    elif ptype == "episode":
        log.info("Neue Episode wird angekündigt.")
        announcer.announce_episode(metadata, thumbnail)
    elif ptype == "track":
        log.info("Neuer Titel wird angekündigt.")
        announcer.announce_track(metadata, thumbnail)
    else:
        log.warning(f"Unbekannter Medientyp: {ptype}")


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=os.environ.get("LOGLEVEL", "INFO"),
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log.debug("Logger initialisiert")

    try:
        config = Config()
        announcer = Announcer(
            config.get_discord_webhook_urls(),
            config.get_plex_server_url(),
            config.get_plex_token(),
        )
        ALLOWED_LIBRARIES = config.get_allowed_libraries()
        PLEX_WEBHOOK_TOKEN = config.get_plex_webhook_token()

        # === Sicherheits-Konfiguration ===
        security = SecurityCheck(
            allowed_ips=config.get_allowed_ips(),
            rate_limit_max=config.get_rate_limit_max(),
            rate_limit_window=config.get_rate_limit_window(),
            require_plex_user_agent=config.get_require_plex_user_agent(),
        )

        # Zusammenfassung loggen
        if config.get_allowed_ips():
            log.info(f"IP-Whitelist aktiv: {config.get_allowed_ips()}")
        else:
            log.warning("Keine IP-Whitelist konfiguriert – alle IPs erlaubt!")
        log.info(
            f"Rate Limit: {config.get_rate_limit_max()} Anfragen / "
            f"{config.get_rate_limit_window()}s"
        )

    except ConfigError as e:
        log.critical(e, exc_info=True)
        exit(-1)

    port = int(os.getenv("PORT", "32500"))
    log.info(f"Plex Webhook URL: http://HOST:{port}/{PLEX_WEBHOOK_TOKEN}")
    log.info("LookArr gestartet und wartet auf Ereignisse...")

    app = web.Application(client_max_size=50 * 1024 * 1024)  # 50MB für große Poster
    app.add_routes([web.post(f"/{PLEX_WEBHOOK_TOKEN}", handle)])
    web.run_app(app, port=port)
