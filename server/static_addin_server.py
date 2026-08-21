"""Small HTTPS static server for the CSM Word add-in.

Why this exists:
- The previous launcher used ``npx http-server`` for port 3000.
- On fresh Windows machines this can fail silently when npm/node_modules/npx
  are not ready, leaving Word with "cannot load add-in" and Chrome with
  ERR_CONNECTION_REFUSED.
- CSM already requires Python for the backend, so this server removes Node from
  the runtime start path. Node is still used during setup to install Office
  development certificates, but the day-to-day add-in server is now Python.

The server binds explicitly to both 127.0.0.1 and ::1 by default. This is more
reliable than relying on a single dual-stack IPv6 socket because Windows,
browser/WebView localhost resolution, and corporate endpoint policies can differ
between machines.
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
from pathlib import Path
import socket
import socketserver
import ssl
import sys
import threading
from typing import Iterator


class CsmStaticHandler(http.server.SimpleHTTPRequestHandler):
    server_version = "CSMStatic/1.1"

    def end_headers(self) -> None:  # noqa: D401 - stdlib override
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))
        sys.stdout.flush()


class ThreadingHttpServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class IPv6LoopbackThreadingHttpServer(ThreadingHttpServer):
    address_family = socket.AF_INET6

    def server_bind(self) -> None:
        # Bind IPv6 as IPv6-only so an IPv4 127.0.0.1 listener can coexist on
        # the same port. This avoids relying on dual-stack behavior.
        with contextlib.suppress(OSError):
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


@contextlib.contextmanager
def make_server(host: str, port: int, handler: type[http.server.BaseHTTPRequestHandler]) -> Iterator[http.server.HTTPServer]:
    server_cls: type[http.server.HTTPServer]
    bind_host = host
    if host in {"::1", "::"}:
        server_cls = IPv6LoopbackThreadingHttpServer
    else:
        server_cls = ThreadingHttpServer
    srv = server_cls((bind_host, port), handler)
    try:
        yield srv
    finally:
        srv.server_close()


def _wrap_server_socket(httpd: http.server.HTTPServer, context: ssl.SSLContext) -> http.server.HTTPServer:
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    return httpd


def _serve_thread(httpd: http.server.HTTPServer) -> threading.Thread:
    t = threading.Thread(target=httpd.serve_forever, name=f"csm-addin-{httpd.server_address}", daemon=False)
    t.start()
    return t


_FORBIDDEN_HOSTS = frozenset({
    "0.0.0.0", "::", "0:0:0:0:0:0:0:0", "*",
})


def _host_candidates(host: str) -> list[str]:
    """Resolve the requested bind host to a concrete IP list.

    Security: the CSM add-in panel contains a session token and exposes
    document content. Binding to a wildcard interface (0.0.0.0 / ::) would
    expose this panel to the local network. The add-in only ever needs to be
    reachable by the Word client on the same machine, so wildcard binds are
    rejected and remapped to safe loopback addresses. A clear warning is
    written to stderr so a misconfigured shortcut is immediately visible.
    """
    if host in {"localhost", "all-localhost", "dual"}:
        return ["127.0.0.1", "::1"]
    if host in _FORBIDDEN_HOSTS:
        sys.stderr.write(
            f"[CSM] Refused to bind add-in HTTPS server to '{host}' (wildcard "
            "interface). Falling back to loopback (127.0.0.1, ::1). The panel "
            "must remain reachable only from the local Word client.\n"
        )
        return ["127.0.0.1", "::1"]
    return [host]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSM HTTPS static add-in server")
    parser.add_argument("--root", required=True, help="Directory with taskpane.html")
    parser.add_argument("--cert", required=True, help="localhost certificate PEM/CRT")
    parser.add_argument("--key", required=True, help="localhost private key PEM")
    parser.add_argument(
        "--host",
        default="all-localhost",
        help=(
            "Bind host (default: all-localhost). Allowed: all-localhost, "
            "localhost, 127.0.0.1, ::1. Wildcard interfaces (0.0.0.0, ::) are "
            "rejected for security — the add-in panel must stay local."
        ),
    )
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    cert = Path(args.cert).resolve()
    key = Path(args.key).resolve()

    if not root.is_dir():
        raise SystemExit(f"Add-in root does not exist or is not a directory: {root}")
    if not (root / "taskpane.html").exists():
        raise SystemExit(f"Missing taskpane.html in add-in root: {root}")
    if not cert.exists():
        raise SystemExit(f"Missing certificate: {cert}")
    if not key.exists():
        raise SystemExit(f"Missing certificate key: {key}")

    handler = functools.partial(CsmStaticHandler, directory=str(root))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))

    servers: list[http.server.HTTPServer] = []
    threads: list[threading.Thread] = []
    errors: list[str] = []

    for bind_host in _host_candidates(args.host):
        try:
            cm = make_server(bind_host, args.port, handler)
            httpd = cm.__enter__()
            # Keep the context manager alive by attaching it to the server; the
            # process normally exits instead of returning from serve_forever,
            # but this lets us close cleanly on KeyboardInterrupt.
            setattr(httpd, "_csm_context_manager", cm)
            _wrap_server_socket(httpd, context)
            servers.append(httpd)
            threads.append(_serve_thread(httpd))
            display_host = "localhost" if bind_host in {"127.0.0.1", "::1"} else bind_host
            print(f"CSM add-in HTTPS server listening on https://{display_host}:{args.port}/ ({bind_host})")
        except OSError as exc:
            errors.append(f"{bind_host}:{args.port} -> {exc}")

    if not servers:
        joined = "; ".join(errors) if errors else "no bind candidates"
        raise SystemExit(f"Unable to start CSM add-in HTTPS server: {joined}")

    print(f"Serving: {root}")
    sys.stdout.flush()

    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        for httpd in servers:
            with contextlib.suppress(Exception):
                httpd.shutdown()
            with contextlib.suppress(Exception):
                httpd.server_close()
            cm = getattr(httpd, "_csm_context_manager", None)
            if cm is not None:
                with contextlib.suppress(Exception):
                    cm.__exit__(None, None, None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
