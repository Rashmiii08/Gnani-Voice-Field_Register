"""Run after stopping the server: python -m scripts.delete_all_data --yes."""

import argparse
from os import getenv

from backend.db import delete_all_records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", required=True, action="store_true")
    args = parser.parse_args()
    print(f"Deleted {delete_all_records(getenv('FIELD_REGISTER_DB'))} local visits.")
