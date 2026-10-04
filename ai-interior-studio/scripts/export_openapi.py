"""Run from the project root: python -m scripts.export_openapi."""
import argparse
import json
from pathlib import Path

from services.api import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('services/api/openapi.json'))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
