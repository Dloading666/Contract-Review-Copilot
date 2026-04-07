"""
Container startup helper.
"""
import os

from .vectorstore.bootstrap import bootstrap_vectorstore


def main() -> None:
    bootstrap_vectorstore()
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "src.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.getenv("PORT", "8000"),
        ],
    )


if __name__ == "__main__":
    main()
