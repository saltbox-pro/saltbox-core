import json
from pathlib import Path

from saltbox_core.main import app


def main() -> None:
    with Path('openapi.json').open('w') as f:
        json.dump(app.openapi(), f, indent=2)


if __name__ == '__main__':
    main()
