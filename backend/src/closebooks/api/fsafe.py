"""Paths and zips that come from outside: nothing leaves the folder it was meant for."""
from __future__ import annotations

import stat
import zipfile
from pathlib import Path, PurePosixPath

from .errors import Problem

MAX_UPLOAD_BYTES = 20 * 2**30


def safe_join(base: Path, relative: str) -> Path | None:
    """`relative` under `base`, or None if it is absolute or escapes (.., symlinks, NUL)."""
    if not relative or "\0" in relative or "\\" in relative or relative.startswith("/"):
        return None
    root = base.resolve()
    target = (root / relative).resolve()
    return target if target.is_relative_to(root) and target != root else None


def extract_zip(archive: Path, destination: Path) -> None:
    """Extract every member under `destination`, refusing zip-slip, symlinks and absurd sizes."""
    destination.mkdir(parents=True)
    root = destination.resolve()
    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            if sum(m.file_size for m in members) > MAX_UPLOAD_BYTES:
                raise Problem(413, "Archive too large")
            for member in members:
                name = member.filename
                posix = PurePosixPath(name)
                if posix.is_absolute() or ".." in posix.parts or "\\" in name or "\0" in name:
                    raise Problem(400, "Unsafe zip", f"Member {name!r} points outside the destination")
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise Problem(400, "Unsafe zip", f"Member {name!r} is a symbolic link")
                target = (root / name).resolve()
                if not target.is_relative_to(root):
                    raise Problem(400, "Unsafe zip", f"Member {name!r} points outside the destination")
            for member in members:
                zf.extract(member, root)
    except zipfile.BadZipFile as exc:
        raise Problem(400, "Not a zip file", str(exc)) from exc
