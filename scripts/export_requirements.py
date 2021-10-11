"""
Exports a generated_requirements.txt file.

Used for several purposes.

WARN: When upgrading the version of poetry used in the dockerfile and workflows,
ensure that this is still compatiable.
"""
import copy
import hashlib
import json
import os
import pathlib
import re
import sys
import textwrap
import typing

import tomli


GENERATED_FILE = pathlib.Path("requirements.txt")

VERSION_RESTRICTER_REGEX = re.compile(r"(?P<sign>[<>=!]{1,2})(?P<version>\d+\.\d+?)(?P<patch>\.\d+?|\.\*)?")
PLATFORM_MARKERS_REGEX = re.compile(r'sys_platform\s?==\s?"(?P<platform>\w+)"')

# fmt: off
MESSAGE = textwrap.indent(textwrap.dedent(
    f"""
    NOTICE: This file is automatically generated by scripts/{__file__.rsplit('/',1)[-1]!s}
    This is also automatically regenerated when an edit to pyproject.toml or poetry.lock is commited.
    """
), '# ').strip()
# fmt: on


def check_hash(hash: str, content: dict) -> bool:
    """Check that the stored hash from the metadata file matches the pyproject.toml file."""
    # OG source: https://github.com/python-poetry/poetry/blob/fe59f689f255ea7f3290daf635aefb0060add056/poetry/packages/locker.py#L44 # noqa: E501
    # This code is as verbatim as possible, with a few changes to be non-object-oriented.

    _relevant_keys = ["dependencies", "dev-dependencies", "source", "extras"]

    def get_hash(content: dict) -> str:
        """Returns the sha256 hash of the sorted content of the pyproject file."""
        content = content["tool"]["poetry"]

        relevant_content = {}
        for key in _relevant_keys:
            relevant_content[key] = content.get(key)

        content_hash = hashlib.sha256(json.dumps(relevant_content, sort_keys=True).encode()).hexdigest()

        return content_hash

    return hash == get_hash(content)


def main(req_path: os.PathLike, should_validate_hash: bool = True) -> typing.Optional[int]:
    """Read and export all required packages to their pinned version in requirements.txt format."""
    req_path = pathlib.Path(req_path)

    with open("pyproject.toml") as f:
        pyproject = tomli.load(f)

    with open("poetry.lock") as f:
        lockfile = tomli.load(f)

    # check hashes
    if should_validate_hash and not check_hash(lockfile["metadata"]["content-hash"], pyproject):
        print("The lockfile is out of date. Please run 'poetry lock'")
        return 2

    pyproject_deps = pyproject["tool"]["poetry"]["dependencies"]

    main_deps = {}
    for package in lockfile["package"]:
        if package["category"] == "main":
            main_deps[package["name"]] = package

    # NOTE: git dependencies are not supported. If a source requires git, this will fail.
    # NOTE: python versions that matter with the platform are not calculated right now
    req_txt = MESSAGE + "\n" * 2
    dependency_lines = {}
    to_add_markers = {}
    for dep in main_deps.values():
        line = ""
        if (pyproject_dep := pyproject_deps.get(dep["name"], None)) is not None and hasattr(
            pyproject_dep, "get"
        ):
            if pyproject_dep.get("git", None) is not None:
                raise NotImplementedError("git sources are not supported")

            elif pyproject_dep.get("url", None) is not None:
                line += " @ " + pyproject_dep["url"]
            else:
                line += "=="
                line += dep["version"]
        else:
            line += "=="
            line += dep["version"]

        if (pyvers := dep["python-versions"]) != "*":
            # TODO: add support for platform and python combined version markers
            line += " ; "
            final_version_index = pyvers.count(", ")
            for count, version in enumerate(pyvers.split(", ")):
                match = VERSION_RESTRICTER_REGEX.match(version)

                if (patch := match.groupdict().get("patch", None)) is not None and not patch.endswith("*"):
                    version_kind = "python_full_version"
                else:
                    version_kind = "python_version"

                patch = patch if patch is not None else ""
                patch = patch if not patch.endswith("*") else ""
                line += version_kind + " "
                line += match.group("sign") + " "
                line += '"' + match.group("version") + patch + '"'
                line += " "
                if count < final_version_index:
                    line += "and "

        if (dep_deps := dep.get("dependencies", None)) is not None:

            for k, v in copy.copy(dep_deps).items():
                if hasattr(v, "get") and v.get("markers", None) is not None:
                    pass
                else:
                    del dep_deps[k]
            if len(dep_deps):
                to_add_markers.update(dep_deps)

        dependency_lines[dep["name"]] = line

    # add the sys_platform lines
    # platform markers only matter based on what requires the dependency
    # in order to support these properly, they have to be added to an already existing line
    # for example, humanfriendly requires pyreadline on windows only,
    # so sys_platform == win needs to be added to pyreadline
    for k, v in to_add_markers.items():
        line = dependency_lines[k]
        markers = PLATFORM_MARKERS_REGEX.match(v["markers"])
        if markers is not None:
            if ";" not in line:
                line += " ; "
            elif "python_" in line or "sys_platform" in line:
                line += "and "
            line += 'sys_platform == "' + markers.group("platform") + '"'
        dependency_lines[k] = line

    req_txt += "\n".join(sorted(k + v.rstrip() for k, v in dependency_lines.items())) + "\n"
    if req_path.exists():
        with open(req_path, "r") as f:
            if req_txt == f.read():
                # nothing to edit
                return 0

    with open(req_path, "w") as f:
        f.write(req_txt)
        print(f"Updated {req_path} with new requirements.")
        return 1


if __name__ == "__main__":
    try:
        skip_hash = bool(int(sys.argv[1]))
    except IndexError:
        skip_hash = False
    sys.exit(main(GENERATED_FILE, should_validate_hash=not skip_hash))
