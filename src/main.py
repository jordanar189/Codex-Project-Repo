"""Launch a local server for the Golf With Your Friends browser game."""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


def main() -> None:
    """Serve the src directory so the game can be played in a browser."""
    root = Path(__file__).parent
    port = 8000
    print(f"Starting game server at http://localhost:{port}/index.html")
    print("Press Ctrl+C to stop.")

    handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(*args, directory=str(root), **kwargs)
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
