from __future__ import annotations

import os


def main() -> None:
    from flask_app import app

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
