#!/usr/bin/env python3
"""
DIUN Webhook Notifier
Listens on a configurable port and sends persistent desktop notifications with sound using D-Bus.
"""

import logging
import os
import json
import sys
import argparse
from http.server import ThreadingHTTPServer as HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(
    filename="/tmp/webhooknotif.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Also log to console
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console.setFormatter(formatter)
logging.getLogger("").addHandler(console)

try:
    import dbus
except ImportError:
    logging.error("dbus-python not installed. Run: pip install dbus-python")
    sys.exit(1)

# Default values
DEFAULT_BASEURL = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_APP_NAME = "Webhook"
DEFAULT_ICON = "preferences-desktop-notification"
DEFAULT_TIMEOUT = 5000  # milliseconds
DEFAULT_URGENCY = "normal"
DEFAULT_DESKTOP_ENTRY = "webhooknotif"
DEFAULT_NOTIFICATION_SOUND = "dialog-information"

# Urgency mapping (string -> int)
URGENCY_MAP = {"low": 0, "normal": 1, "critical": 2}


def send_notification(
    summary,
    body,
    app_name,
    icon,
    timeout,
    urgency,
    desktop_entry,
    sound_name=None,
    sound_file=None,
):
    """Send a notification via D‑Bus with the given parameters."""

    bus = dbus.SessionBus()
    notify_obj = bus.get_object(
        "org.freedesktop.Notifications", "/org/freedesktop/Notifications"
    )
    interface = dbus.Interface(notify_obj, "org.freedesktop.Notifications")

    hints = {
        "transient": dbus.Boolean(False, variant_level=1),
        "urgency": dbus.Byte(urgency, variant_level=1),
        "desktop-entry": dbus.String(desktop_entry, variant_level=1),
    }

    # Add sound hints if provided
    if sound_name:
        hints["sound-name"] = dbus.String(sound_name, variant_level=1)
    if sound_file:
        hints["sound-file"] = dbus.String(sound_file, variant_level=1)

    interface.Notify(
        app_name,  # app_name
        0,  # replaces_id
        icon,  # app_icon
        summary,  # summary
        body,  # body
        [],  # actions
        hints,  # hints
        timeout,  # timeout
    )


def ensure_desktop_file(desktop_entry):
    """
    Create a .desktop file for the given desktop entry name if it doesn't exist.
    The file is created in ~/.local/share/applications/.
    """
    home = os.path.expanduser("~")
    apps_dir = os.path.join(home, ".local", "share", "applications")
    desktop_path = os.path.join(apps_dir, f"{desktop_entry}.desktop")

    if os.path.exists(desktop_path):
        logging.debug(f"Desktop file already exists: {desktop_path}")
        return

    # Ensure the applications directory exists
    try:
        os.makedirs(apps_dir, exist_ok=True)
    except OSError as e:
        logging.error(f"Failed to create directory {apps_dir}: {e}")
        return

    # Desktop entry content
    content = f"""[Desktop Entry]
Type=Application
Name=Webhook Notifier
Comment=Receive webhook notifications and display them via D-Bus
Icon={DEFAULT_ICON}
NoDisplay=true
"""
    try:
        with open(desktop_path, "w", encoding="utf-8") as f:
            f.write(content)
        logging.info(f"Created desktop file: {desktop_path}")
    except OSError as e:
        logging.error(f"Failed to write desktop file {desktop_path}: {e}")


class WebhookHandler(BaseHTTPRequestHandler):
    app_name = DEFAULT_APP_NAME
    icon = DEFAULT_ICON
    timeout = DEFAULT_TIMEOUT
    urgency_int = URGENCY_MAP[DEFAULT_URGENCY]
    desktop_entry = DEFAULT_DESKTOP_ENTRY
    notification_sound = DEFAULT_NOTIFICATION_SOUND

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            logging.error("Invalid JSON received")
            return

        logging.info("Received payload:")
        logging.info(json.dumps(payload, indent=2))

        title = None
        body = None
        app_name = self.app_name
        icon = self.icon
        timeout = self.timeout
        urgency = self.urgency_int
        desktop_entry = self.desktop_entry
        notification_sound = self.notification_sound

        if "diun_version" in payload:
            if payload.get("status") == "new":
                image = payload.get("image", "")
                host = payload.get("hostname", "device")

                metadata = payload.get("metadata") or {}
                container_names = metadata.get("ctn_names")

                if isinstance(container_names, list):
                    container = ", ".join(container_names)
                elif container_names:
                    container = str(container_names)
                else:
                    container = "unknown"

                title = "Docker Image Update"
                body = f"Docker Image update available for Container:{container} Image:{image} on {host}"
                app_name = "DIUN"
                logging.info(f"Payload Type: {app_name}")
                icon = "docker-desktop"
                timeout = 5000
                urgency = self.urgency_int
                desktop_entry = self.desktop_entry
                notification_sound = self.notification_sound

            else:
                logging.info("Ignored non‑new status")

        else:
            title = payload.get("title")
            body = payload.get("body")
            app_name = payload.get("app_name", self.app_name)
            logging.info(f"Payload Type: {app_name}")
            icon = payload.get("icon", self.icon)
            timeout_raw = payload.get("timeout")
            if timeout_raw is not None:
                try:
                    timeout = int(timeout_raw)
                except (ValueError, TypeError):
                    timeout = self.timeout
                    logging.warning(
                        f"Invalid timeout value '{timeout_raw}', using default {self.timeout}"
                    )
            else:
                timeout = self.timeout

            urgency_str = payload.get("urgency")
            if urgency_str and urgency_str in URGENCY_MAP:
                urgency = URGENCY_MAP[urgency_str]
            else:
                urgency = self.urgency_int

            desktop_entry = payload.get("desktop_entry", self.desktop_entry)
            notification_sound = payload.get(
                "notification_sound", self.notification_sound
            )

        if title and body:
            try:
                sound_name = None
                sound_file = None
                if notification_sound:
                    if "/" in notification_sound:
                        sound_file = notification_sound
                    else:
                        sound_name = notification_sound

                send_notification(
                    title,
                    body,
                    app_name=app_name,
                    icon=icon,
                    timeout=timeout,
                    urgency=urgency,
                    desktop_entry=desktop_entry,
                    sound_name=sound_name,
                    sound_file=sound_file,
                )

                sound_info = (
                    f" (Notification Sound: {notification_sound})"
                    if notification_sound
                    else ""
                )
                logging.info(f"Notification sent{sound_info}: {title} - {body}")
            except Exception as e:
                logging.error(f"D‑Bus error: {e}")
        else:
            logging.warning("No notification sent: missing title or body")

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        """Override to suppress default HTTP request logging."""
        _ = (format, args)  # Mark parameters as used to silence linter warnings
        pass


def main():
    if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
        uid = os.getuid()
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"

    parser = argparse.ArgumentParser(
        description="Webhook Notification Handler (D‑Bus with sound)",
        epilog=f"""\
Default values (used if not overridden in generic payload):
  app_name:             {DEFAULT_APP_NAME!r}
  icon:                 {DEFAULT_ICON!r} (icon name or file path)
  timeout:              {DEFAULT_TIMEOUT} ms
  urgency:              {DEFAULT_URGENCY!r} → maps to {URGENCY_MAP[DEFAULT_URGENCY]} (allowed: low, normal, critical)
  desktop_entry:        {DEFAULT_DESKTOP_ENTRY!r} (desktop file name without .desktop)
  notification_sound:   {DEFAULT_NOTIFICATION_SOUND!r} (sound name or file path)

Examples:

1. Generic payload (overridable parameters shown):
{{
  "title": "Test Notification",
  "body": "This is a test.",
  "app_name": "MyCustomApp",
  "icon": "dialog-information",
  "timeout": 5000,
  "urgency": "critical",
  "desktop_entry": "firefox",
  "notification_sound": "message-new-instant"
   # or "notification_sound": "/path/to/custom.wav"   # custom sound file
}}

2. DIUN‑format payload (triggers a "Docker Image Update" notification):
{{
  "diun_version": "4.25.1",
  "status": "new",
  "image": "docker.io/library/nginx:latest",
  "hostname": "my-server",
  "metadata": {{
    "ctn_names": ["nginx-proxy", "web-frontend"]
  }}
}}

Note: 
=> For generic payloads, all fields except "title" and "body" are optional; omitted fields use the defaults shown at startup.
=> For notifications to appear in Notification history, the "desktop-entry" must match an existing .desktop file (e.g., ~/.local/share/applications/com.github.wintersnowgod.webhooknotif.desktop).
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--baseurl",
        default=DEFAULT_BASEURL,
        help=f"Address to listen on (default: {DEFAULT_BASEURL})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )

    args = parser.parse_args()

    ensure_desktop_file(DEFAULT_DESKTOP_ENTRY)

    server = HTTPServer((args.baseurl, args.port), WebhookHandler)
    logging.info(f"Listening on {args.baseurl}:{args.port}...")
    logging.info(f"App name: {DEFAULT_APP_NAME}")
    logging.info(f"Icon: {DEFAULT_ICON}")
    logging.info(f"Timeout: {DEFAULT_TIMEOUT} ms")
    logging.info(f"Urgency: {DEFAULT_URGENCY} ({URGENCY_MAP[DEFAULT_URGENCY]})")
    logging.info(f"Desktop entry: {DEFAULT_DESKTOP_ENTRY}")
    logging.info(
        f"Notification sound: {DEFAULT_NOTIFICATION_SOUND} (interpreted as {'file' if '/' in DEFAULT_NOTIFICATION_SOUND else 'themed name'})"
    )
    logging.info(
        "Make sure the corresponding .desktop file exists if you want notifications to persist in notification history."
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
