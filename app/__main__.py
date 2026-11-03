import sys

import uvicorn

from .config import check_config, load_config


def main() -> None:
    cfg = load_config()
    problems = check_config(cfg)
    if problems:
        sys.stderr.write("Preisschnapsen cannot start:\n")
        for p in problems:
            sys.stderr.write("  - " + p + "\n")
        sys.stderr.write("Set the passwords with: schnapsen-passwd admin  /  schnapsen-passwd user\n")
        sys.exit(2)
    from .main import create_app

    # timeout_graceful_shutdown: open SSE connections never close on their own, so a stop
    # would otherwise wait until systemd kills the process.
    # access_log is off because the dashboard polls every few seconds.
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="info", proxy_headers=False,
                timeout_graceful_shutdown=3, access_log=False)


if __name__ == "__main__":
    main()
