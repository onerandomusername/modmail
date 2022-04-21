"""
Exports the configuration to the configuration default files.

This is intended to be used as a local pre-commit hook, which runs if the modmail/config.py file is changed.
"""
import difflib
import json
import os
import pathlib
import sys
import textwrap
import typing
from collections import defaultdict

import atoml
import attr
import click
import dotenv
import yaml


try:
    import pygments
except ModuleNotFoundError:
    pygments = None
else:
    from pygments.lexers.diff import DiffLexer
    from pygments.formatters import Terminal256Formatter

import modmail
import modmail.config


MODMAIL_CONFIG_DIR = pathlib.Path(modmail.config.__file__).parent
ENV_EXPORT_FILE = MODMAIL_CONFIG_DIR.parent / "template.env"
APP_JSON_FILE = MODMAIL_CONFIG_DIR.parent / "app.json"

METADATA_TABLE = modmail.config.METADATA_TABLE
MODMAIL_DIR = pathlib.Path(modmail.__file__).parent


def get_name(path: str) -> str:
    """Get the script module name of the provided file path."""
    p = pathlib.Path(__file__)
    p = p.relative_to(MODMAIL_DIR.parent)
    name = str(p)
    if name.endswith(p.suffix):
        name = name[: -len(p.suffix)]
    name = name.replace("/", ".")
    return name


# fmt: off
MESSAGE = textwrap.indent(textwrap.dedent(
    f"""
        This is an autogenerated {{file_type}} document.
        Run module '{get_name(__file__)}' to generate.
    """
), "# ").strip() + "\n"
# fmt: on


class MetadataDict(typing.TypedDict):
    """Typed metadata. This has a possible risk given that the modmail_metadata variable is defined."""

    modmail_metadata: modmail.config.ConfigMetadata
    required: bool


class DidFileEdit:
    """Check if a file is edited within the body of this class."""

    def __init__(self, *files: os.PathLike):
        self.files: typing.List[os.PathLike] = []
        for f in files:
            self.files.append(f)
        self.return_value: typing.Optional[int] = None
        self.edited_files: typing.Dict[os.PathLike] = dict()

    def __enter__(self):
        self.file_contents = {}
        for file in self.files:
            try:
                with open(file, "r") as f:
                    self.file_contents[file] = f.readlines()
            except FileNotFoundError:
                self.file_contents[file] = None
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):  # noqa: ANN001
        for file in self.files:
            with open(file, "r") as f:
                original_contents = self.file_contents[file]
                new_contents = f.readlines()
                if original_contents != new_contents:
                    # construct a diff
                    diff = difflib.unified_diff(
                        original_contents, new_contents, fromfile="before", tofile="after"
                    )
                    try:
                        diff = "".join(diff)
                    except TypeError:
                        diff = None
                    else:
                        if pygments is not None:
                            diff = pygments.highlight(diff, DiffLexer(), Terminal256Formatter())
                    self.edited_files[file] = diff


def export_default_conf() -> int:
    """Export default configuration as both toml and yaml to the preconfigured locations."""
    default = modmail.config.get_default_config()
    dump: dict = modmail.config.ConfigurationSchema().dump(default)

    # Sort the dictionary configuration.
    # This is the only place where the order of the config should matter, when exporting in a specific style
    def sort_dict(d: dict) -> dict:
        """Takes a dict and sorts it, recursively."""
        sorted_dict = {x[0]: x[1] for x in sorted(d.items(), key=lambda e: e[0])}

        for k, v in d.items():
            if not isinstance(v, dict):
                continue
            sorted_dict[k] = sort_dict(v)

        return sorted_dict

    dump = sort_dict(dump)
    doc = atoml.document()
    doc.update(dump)

    toml_file = MODMAIL_CONFIG_DIR / (modmail.config.AUTO_GEN_FILE_NAME + ".toml")
    yaml_file = MODMAIL_CONFIG_DIR / (modmail.config.AUTO_GEN_FILE_NAME + ".yaml")

    with DidFileEdit(toml_file, yaml_file) as check_file:
        with open(toml_file, "w") as f:
            f.write(MESSAGE.format(file_type="TOML"))
            f.write("\n")
            atoml.dump(doc, f)

        with open(yaml_file, "w") as f:
            f.write(MESSAGE.format(file_type="YAML"))
            yaml.dump(dump, f, indent=4, Dumper=yaml.SafeDumper)

    for file, diff in check_file.edited_files.items():
        print(
            f"Exported new configuration to {pathlib.Path(file).relative_to(MODMAIL_DIR.parent)}.",
            file=sys.stderr,
        )
        if diff is not None:
            click.echo(diff)
        else:
            click.echo("No diff to show.")
        print()
    return bool(len(check_file.edited_files))


def export_env_and_app_json_conf() -> int:
    """
    Exports required configuration variables to .env.template.

    Does NOT export *all* settable variables!

    Export the *required* environment variables to `.env.template`.
    Required environment variables are any Config.default variables that default to marshmallow.missing
    These can also be configured by using the ConfigMetadata options.
    """
    default = modmail.config.get_default_config()

    # find all environment variables to report
    def get_env_vars(klass: type, env_prefix: str = None) -> typing.Dict[str, MetadataDict]:

        if env_prefix is None:
            env_prefix = modmail.config.ENV_PREFIX

        # exact name, default value
        export: typing.Dict[str, MetadataDict] = dict()  # any missing required vars provide a sentinel

        for var in attr.fields(klass):
            if attr.has(var.type):
                # var is an attrs class too, recurse over it
                export.update(
                    get_env_vars(
                        var.type,
                        env_prefix=env_prefix + var.name.upper() + "_",
                    )
                )
            else:
                meta: MetadataDict = var.metadata
                # put all values in the dict, we'll iterate through them later.
                export[env_prefix + var.name.upper()] = meta

        return export

    with DidFileEdit(ENV_EXPORT_FILE, APP_JSON_FILE) as check_file:
        # parse the app_json file before clearing the ENV file
        with open(APP_JSON_FILE) as f:
            try:
                app_json: typing.Dict = json.load(f)
            except Exception as e:
                print(
                    "Oops! Please ensure the app.json file is valid json! "
                    "If you've made manual edits, you may want to revert them.",
                    file=sys.stderr,
                )
                raise e

        # dotenv modifies currently existing files, but we want to erase the current file
        # to ensure that there are no extra environment variables
        ENV_EXPORT_FILE.unlink(missing_ok=True)
        ENV_EXPORT_FILE.touch()

        exported = get_env_vars(type(default))

        app_json_env = dict()

        for key, meta in exported.items():
            # if the value is required, or explicity asks to be exported, then we want to export it
            if meta[METADATA_TABLE].export_to_env_template or meta.get("required", False):

                dotenv.set_key(
                    ENV_EXPORT_FILE,
                    key,
                    meta[METADATA_TABLE].export_environment_prefill or meta["default"],
                )

            if (
                meta[METADATA_TABLE].export_to_app_json
                or meta[METADATA_TABLE].export_to_env_template
                or meta.get("required", False)
            ):
                description = (
                    f"{meta[METADATA_TABLE].description}\n{meta[METADATA_TABLE].extended_description or ''}"
                ).strip()
                options = defaultdict(
                    str,
                    {
                        "description": description,
                        "required": meta[METADATA_TABLE].app_json_required or meta.get("required", False),
                    },
                )
                if (value := meta[modmail.config.METADATA_TABLE].app_json_default) is not None:
                    options["value"] = value
                app_json_env[key] = options

        app_json["env"] = app_json_env
        with open(APP_JSON_FILE, "w") as f:
            json.dump(app_json, f, indent=4)
            f.write("\n")

    for file, diff in check_file.edited_files.items():
        print(
            f"Exported new env configuration to {pathlib.Path(file).relative_to(MODMAIL_DIR.parent)}.",
            file=sys.stderr,
        )
        if diff is not None:
            click.echo(diff)
        else:
            click.echo("No diff to show.")
        print()
    return bool(len(check_file.edited_files))


def main() -> int:
    """
    Exports the default configuration.

    There's several parts to this export.
    First, export the default configuration to the default locations.

    Next, export the *required* configuration variables to the .env.template

    In addition, export to app.json when exporting .env.template.
    """
    exit_code = export_default_conf()

    return export_env_and_app_json_conf() or exit_code


if __name__ == "__main__":
    sys.exit(main())
