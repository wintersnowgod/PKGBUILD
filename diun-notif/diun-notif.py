#!/usr/bin/env python3
"""
DIUN Webhook Notifier
Listens on a configurable port and sends persistent desktop notifications with sound using D-Bus.
"""

import json
import sys
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import dbus
except ImportError:
    print(
        "Error: dbus-python not installed. Run: pip install dbus-python",
        file=sys.stderr,
    )
    sys.exit(1)

# Default values
DEFAULT_PORT = 9999
DEFAULT_APP_NAME = "DIUN"
DEFAULT_ICON = "docker-desktop"
DEFAULT_TIMEOUT = 5000  # milliseconds
DEFAULT_URGENCY = "normal"
DEFAULT_DESKTOP_ENTRY = "diun-notif"
DEFAULT_SOUND_NAME = "dialog-information"
DEFAULT_SOUND_FILE = None

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


class WebhookHandler(BaseHTTPRequestHandler):
    # Class variables to hold configuration (set by main())
    app_name = DEFAULT_APP_NAME
    icon = DEFAULT_ICON
    timeout = DEFAULT_TIMEOUT
    urgency_int = URGENCY_MAP[DEFAULT_URGENCY]
    desktop_entry = DEFAULT_DESKTOP_ENTRY
    sound_name = DEFAULT_SOUND_NAME
    sound_file = DEFAULT_SOUND_FILE

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length)

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return

        if payload.get("status") == "new":
            image = payload.get("image", "")
            metadata = payload.get("metadata")

            # Container name: try metadata.ctn_names, else parse from image
            if isinstance(metadata, dict) and metadata.get("ctn_names"):
                container = metadata["ctn_names"]
            else:
                base = image.split("/")[-1]  # after last slash
                container = base.split(":")[0]  # before colon
                if not container:
                    container = "unknown"

            version = image.split(":")[-1] if ":" in image else "unknown"

            title = "Docker Image Update"
            body = f"Update Available for Container: {container} Image -> new version: {version}"

            try:
                send_notification(
                    title,
                    body,
                    app_name=self.app_name,
                    icon=self.icon,
                    timeout=self.timeout,
                    urgency=self.urgency_int,
                    desktop_entry=self.desktop_entry,
                    sound_name=self.sound_name,
                    sound_file=self.sound_file,
                )
                sound_info = (
                    f" (sound: {self.sound_name or self.sound_file})"
                    if (self.sound_name or self.sound_file)
                    else ""
                )
                print(f"Notification sent{sound_info}: {title} - {body}")
            except Exception as e:
                print(f"D‑Bus error: {e}", file=sys.stderr)
        else:
            print("Ignored non‑new status")

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        """Override to suppress default HTTP request logging."""
        _ = (format, args)  # Mark parameters as used to silence linter warnings
        pass


def main():
    parser = argparse.ArgumentParser(
        description="DIUN webhook notifier (D‑Bus with sound)",
        epilog="Note: For notifications to appear in KDE history, the --desktop-entry must match an existing .desktop file (e.g., ~/.local/share/applications/diun-notif.desktop).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--app-name",
        default=DEFAULT_APP_NAME,
        help=f"Application name (default: {DEFAULT_APP_NAME})",
    )
    parser.add_argument(
        "--icon",
        default=DEFAULT_ICON,
        help=f"Icon name or path (default: {DEFAULT_ICON})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Notification timeout in ms (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--urgency",
        choices=["low", "normal", "critical"],
        default=DEFAULT_URGENCY,
        help=f"Urgency level (default: {DEFAULT_URGENCY})",
    )
    parser.add_argument(
        "--desktop-entry",
        default=DEFAULT_DESKTOP_ENTRY,
        help=f"Desktop file name without .desktop (default: {DEFAULT_DESKTOP_ENTRY})",
    )
    parser.add_argument(
        "--sound-name",
        default=DEFAULT_SOUND_NAME,
        help=f"Themed sound name to play (default: {DEFAULT_SOUND_NAME})",
    )
    parser.add_argument(
        "--sound-file",
        default=DEFAULT_SOUND_FILE,
        help="Path to a custom sound file (overrides --sound-name)",
    )
    args = parser.parse_args()

    # Set handler configuration
    WebhookHandler.app_name = args.app_name
    WebhookHandler.icon = args.icon
    WebhookHandler.timeout = args.timeout
    WebhookHandler.urgency_int = URGENCY_MAP[args.urgency]
    WebhookHandler.desktop_entry = args.desktop_entry
    WebhookHandler.sound_name = args.sound_name
    WebhookHandler.sound_file = args.sound_file

    server = HTTPServer(("", args.port), WebhookHandler)
    print(f"Listening on port {args.port}...")
    print(f"App name: {args.app_name}")
    print(f"Icon: {args.icon}")
    print(f"Timeout: {args.timeout} ms")
    print(f"Urgency: {args.urgency} ({WebhookHandler.urgency_int})")
    print(f"Desktop entry: {args.desktop_entry}")
    if args.sound_file:
        print(f"Sound file: {args.sound_file}")
    else:
        print(f"Sound name: {args.sound_name}")
    print(
        "Make sure the corresponding .desktop file exists if you want notifications to persist in notification history."
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
