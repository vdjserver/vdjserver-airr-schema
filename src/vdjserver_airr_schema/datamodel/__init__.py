"""Data model package for vdjserver-airr-schema."""

from pathlib import Path
from .vdjserver_airr_schema import *  # noqa: F403

THIS_PATH = Path(__file__).parent

SCHEMA_DIRECTORY = THIS_PATH.parent / "schema"
MAIN_SCHEMA_PATH = SCHEMA_DIRECTORY / "vdjserver_airr_schema.yaml"
