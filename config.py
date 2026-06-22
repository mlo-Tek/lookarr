import os
import yaml
import logging

log = logging.getLogger("config")


class ConfigError(Exception):
    pass


class Config:
    def __init__(self):
        self._data = {}

        config_path = "/config/config.yaml"
        if os.path.exists(config_path):
            log.info(f"Lade Konfiguration aus {config_path}")
            with open(config_path, "r") as f:
                self._data = yaml.safe_load(f) or {}
        else:
            log.info("Kein config.yaml gefunden – nutze Umgebungsvariablen")

    def _get(self, key_json, key_env, required=True):
        value = self._data.get(key_json) or os.environ.get(key_env)
        if required and not value:
            raise ConfigError(
                f"Fehlende Konfiguration: '{key_json}' in config.yaml "
                f"oder Umgebungsvariable '{key_env}'"
            )
        return value

    def get_plex_server_url(self):
        return self._get("plex_server_url", "PLEX_SERVER_URL")

    def get_plex_token(self):
        # Optional – wird für Poster-URLs benötigt
        return self._get("plex_token", "PLEX_TOKEN", required=False)

    def get_plex_webhook_token(self):
        return self._get("plex_webhook_token", "PLEX_WEBHOOK_TOKEN")

    def get_discord_webhook_urls(self):
        value = self._data.get("discord_webhook_urls") or os.environ.get(
            "DISCORD_WEBHOOK_URLS"
        )
        if not value:
            # Fallback: einzelne URL
            single = self._get("discord_webhook_url", "DISCORD_WEBHOOK_URL")
            return [single]
        if isinstance(value, list):
            return value
        # Komma-getrennte Umgebungsvariable
        return [v.strip() for v in value.split(",")]

    def get_allowed_libraries(self):
        value = self._data.get("allowed_libraries") or os.environ.get(
            "ALLOWED_LIBRARIES"
        )
        if not value:
            return []
        if isinstance(value, list):
            return value
        return [v.strip() for v in value.split(",")]

    # ------------------------------------------------------------------ #
    #  Sicherheits-Einstellungen                                            #
    # ------------------------------------------------------------------ #

    def get_allowed_ips(self):
        """Liste erlaubter IPs/Netze. Leer = alle erlaubt."""
        value = self._data.get("allowed_ips") or os.environ.get("ALLOWED_IPS")
        if not value:
            return []
        if isinstance(value, list):
            return value
        return [v.strip() for v in value.split(",")]

    def get_rate_limit_max(self):
        """Max. Anfragen pro Zeitfenster (Standard: 60)."""
        value = self._data.get("rate_limit_max") or os.environ.get("RATE_LIMIT_MAX")
        try:
            return int(value) if value else 60
        except ValueError:
            return 60

    def get_rate_limit_window(self):
        """Zeitfenster in Sekunden (Standard: 60)."""
        value = self._data.get("rate_limit_window") or os.environ.get(
            "RATE_LIMIT_WINDOW"
        )
        try:
            return int(value) if value else 60
        except ValueError:
            return 60

    def get_require_plex_user_agent(self):
        """User-Agent-Filter aktivieren (Standard: True)."""
        value = self._data.get("require_plex_user_agent")
        if value is None:
            value = os.environ.get("REQUIRE_PLEX_USER_AGENT", "true")
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")

    def get_send_test_message(self):
        """Test-Nachricht beim Start senden (Standard: False)."""
        value = self._data.get("send_test_message")
        if value is None:
            value = os.environ.get("SEND_TEST_MESSAGE", "false")
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
