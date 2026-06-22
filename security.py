"""
Sicherheits-Helfer für LookArr.

Plex-Webhooks haben keine HMAC-Signatur. Wir nutzen daher mehrere Schichten:
- IP-Whitelist: nur Anfragen von erlaubten IPs zulassen
- Rate Limit: zu viele Anfragen pro IP/Zeitfenster blockieren
- User-Agent-Filter: Plex sendet "PlexMediaServer/..." als User-Agent
- Payload-Validierung: prüfen ob die Anfrage wirklich nach einem Plex-Webhook aussieht
"""

import time
import ipaddress
import logging
from collections import defaultdict, deque
from aiohttp import web

log = logging.getLogger("security")


class SecurityCheck:
    """
    Kapselt alle Sicherheitsprüfungen für eingehende Webhook-Anfragen.

    Alle Features sind optional und können einzeln aktiviert werden.
    """

    def __init__(
        self,
        allowed_ips: list = None,
        rate_limit_max: int = 60,
        rate_limit_window: int = 60,
        require_plex_user_agent: bool = True,
    ):
        # IP-Whitelist – leere Liste = alle IPs erlaubt
        self.allowed_networks = []
        if allowed_ips:
            for entry in allowed_ips:
                try:
                    # Unterstützt einzelne IPs ("192.168.1.10") und Netze ("192.168.1.0/24")
                    self.allowed_networks.append(
                        ipaddress.ip_network(entry, strict=False)
                    )
                except ValueError as e:
                    log.warning(f"Ungültige IP-Whitelist-Angabe '{entry}': {e}")

        # Rate Limit: max. N Anfragen pro Zeitfenster (Sekunden) je IP
        self.rate_limit_max = rate_limit_max
        self.rate_limit_window = rate_limit_window
        self._request_log: dict = defaultdict(deque)
        # Damit der Speicher bei vielen unterschiedlichen IPs nicht unbegrenzt wächst,
        # bereinigen wir alte Einträge regelmäßig.
        self._last_cleanup = time.time()
        self._cleanup_interval = 300  # alle 5 Minuten
        self._max_tracked_ips = 10000  # harter Deckel als zusätzlicher Schutz

        self.require_plex_user_agent = require_plex_user_agent

    # ------------------------------------------------------------------ #

    def _get_client_ip(self, request: web.Request) -> str:
        """
        Ermittelt die echte Client-IP.
        Berücksichtigt X-Forwarded-For für Reverse-Proxy-Setups (z.B. Nginx Proxy Manager).
        """
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For kann eine Kette sein: "client, proxy1, proxy2"
            # Die erste IP ist der ursprüngliche Client.
            return forwarded.split(",")[0].strip()
        return request.remote or "unknown"

    # ------------------------------------------------------------------ #

    def check_ip_whitelist(self, request: web.Request) -> bool:
        """True wenn die IP erlaubt ist (oder die Whitelist leer ist)."""
        if not self.allowed_networks:
            return True

        client_ip_str = self._get_client_ip(request)
        try:
            client_ip = ipaddress.ip_address(client_ip_str)
        except ValueError:
            log.warning(f"Ungültige Client-IP erhalten: {client_ip_str}")
            return False

        for network in self.allowed_networks:
            if client_ip in network:
                return True

        log.warning(f"IP nicht in Whitelist abgelehnt: {client_ip_str}")
        return False

    # ------------------------------------------------------------------ #

    def check_rate_limit(self, request: web.Request) -> bool:
        """
        True wenn die IP unter dem Limit liegt.
        Speichert Zeitstempel pro IP im rollenden Fenster.
        """
        client_ip = self._get_client_ip(request)
        now = time.time()
        window_start = now - self.rate_limit_window

        # Periodische Bereinigung: IPs ohne aktive Zeitstempel komplett entfernen.
        # Verhindert unbegrenztes Wachstum bei vielen verschiedenen IPs.
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup_request_log(window_start)
            self._last_cleanup = now

        # Notbremse: falls trotz Bereinigung zu viele IPs getrackt sind.
        if len(self._request_log) >= self._max_tracked_ips and client_ip not in self._request_log:
            log.warning(
                f"Maximale getrackte IPs ({self._max_tracked_ips}) erreicht – "
                f"neue IP {client_ip} wird vorerst abgelehnt"
            )
            return False

        timestamps = self._request_log[client_ip]
        # Alte Einträge raus
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= self.rate_limit_max:
            log.warning(
                f"Rate Limit überschritten für {client_ip}: "
                f"{len(timestamps)}/{self.rate_limit_max} in {self.rate_limit_window}s"
            )
            return False

        timestamps.append(now)
        return True

    def _cleanup_request_log(self, window_start: float):
        """Entfernt IPs ohne aktive Zeitstempel aus dem Speicher."""
        to_delete = []
        for ip, timestamps in self._request_log.items():
            while timestamps and timestamps[0] < window_start:
                timestamps.popleft()
            if not timestamps:
                to_delete.append(ip)
        for ip in to_delete:
            del self._request_log[ip]
        if to_delete:
            log.debug(f"Rate-Limit-Cleanup: {len(to_delete)} IPs entfernt")

    # ------------------------------------------------------------------ #

    def check_user_agent(self, request: web.Request) -> bool:
        """
        True wenn User-Agent von Plex stammt.
        Plex sendet z.B. "PlexMediaServer/1.32.0.7227-bd9ee0e6a"
        Hinweis: User-Agents lassen sich fälschen – das ist nur eine zusätzliche Hürde.
        """
        if not self.require_plex_user_agent:
            return True

        ua = request.headers.get("User-Agent", "")
        if "PlexMediaServer" in ua:
            return True

        log.warning(f"Anfrage abgelehnt: User-Agent nicht von Plex ('{ua}')")
        return False

    # ------------------------------------------------------------------ #

    def check_content_type(self, request: web.Request) -> bool:
        """True wenn Content-Type multipart/form-data ist (wie Plex es sendet)."""
        ct = request.content_type or ""
        if ct == "multipart/form-data":
            return True
        log.info(f"Anfrage abgelehnt: Content-Type '{ct}' (nicht von Plex)")
        return False

    # ------------------------------------------------------------------ #

    def run_pre_checks(self, request: web.Request):
        """
        Führt alle Prüfungen aus die vor dem Lesen des Bodys möglich sind.
        Gibt None zurück wenn alles ok ist, sonst eine aiohttp Response.
        """
        # Rate Limit zuerst – auch fehlerhafte Anfragen sollen begrenzt sein
        if not self.check_rate_limit(request):
            return web.Response(status=429, text="Too Many Requests")

        # IP-Whitelist
        if not self.check_ip_whitelist(request):
            return web.Response(status=403, text="Forbidden")

        # User-Agent
        if not self.check_user_agent(request):
            return web.Response(status=403, text="Forbidden")

        # Content-Type
        if not self.check_content_type(request):
            return web.Response(status=400, text="Bad Request")

        return None

    # ------------------------------------------------------------------ #

    def validate_payload(self, metadata: dict) -> bool:
        """
        Plausibilitätsprüfung: hat das JSON die erwarteten Felder eines Plex-Webhooks?
        """
        if not isinstance(metadata, dict):
            return False
        # Plex-Webhooks haben immer 'event' und 'Server' (mit 'uuid')
        if "event" not in metadata:
            log.warning("Payload-Validierung fehlgeschlagen: 'event' fehlt")
            return False
        if "Server" not in metadata or "uuid" not in metadata.get("Server", {}):
            log.warning("Payload-Validierung fehlgeschlagen: 'Server.uuid' fehlt")
            return False
        return True
