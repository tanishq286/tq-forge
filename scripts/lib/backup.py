"""Backup, apply and restore for the context optimizer (Python stdlib only).

Every `--apply` goes through `apply_writes`, which keeps what `restore` needs
in <root>/.tq-forge-backup/:

  <path>                    the original of each file that was changed
  symlink-targets/<path>    the original of a file reached through a symlink
  manifest.json             {"created": [...],          files to delete on restore
                             "created_hashes": {...},   file -> SHA-256 of what was written
                             "symlink_targets": {...},  file -> its backup
                             "removed_links": {...}}    symlink -> where it pointed

A created file is deleted on restore only while it still holds exactly what the
apply wrote. If you edited it since, restore keeps it and says so.

The first backup of a file wins, so `restore` always goes back to the state
before the first apply, however many applies followed.

`restore` trusts the manifest only inside the root. A file outside it (the
target of a followed symlink) is restored only with `outside=True`, so a
backup folder that arrived with a cloned project cannot make `restore` write
or delete somewhere else on the machine. For the same reason neither function
works with a backup folder that is, or contains, a symlink, and `restore`
never copies onto a symlink.
"""

import hashlib
import json
import os
import pathlib
import shutil

import context_cost
import scaffold

BACKUP_DIR = ".tq-forge-backup"
MANIFEST = "manifest.json"
LINK_BACKUPS = "symlink-targets"


def is_absolute(key):
    return pathlib.PurePosixPath(str(key)).is_absolute()


def _within(folder, path):
    """True when the real location of `path` is `folder` or sits under it."""
    real_folder, real_path = os.path.realpath(folder), os.path.realpath(path)
    try:
        return os.path.commonpath([real_folder, real_path]) == real_folder
    except ValueError:  # different drives
        return False


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_digest(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _refuse_links(backup_root):
    """Stop when the backup folder is, or holds, a symlink: a copy through one lands outside it."""
    if backup_root.is_symlink():
        raise scaffold.ScaffoldError(f"{backup_root} is a symlink; remove it before running tq-forge here")
    for folder, folders, files in os.walk(backup_root, followlinks=False):
        for name in (*folders, *files):
            if os.path.islink(os.path.join(folder, name)):
                raise scaffold.ScaffoldError(
                    f"{os.path.join(folder, name)} is a symlink inside {BACKUP_DIR}/; "
                    f"remove {BACKUP_DIR}/ before running tq-forge here")


def apply_writes(root, writes, backup=True, aliases=None, remove_links=None):
    """Write a plan into `root`. `backup=False` is the preview run on a scratch copy."""
    aliases, remove_links = aliases or {}, remove_links or {}
    backup_root = root / BACKUP_DIR
    if backup:
        _refuse_links(backup_root)
    manifest = context_cost.load_json(backup_root / MANIFEST)
    created = list(manifest.get("created", []))
    link_targets = dict(manifest.get("symlink_targets") or {})
    removed = dict(manifest.get("removed_links") or {})
    hashes = dict(manifest.get("created_hashes") or {})
    # Phase 1: back everything up and record it, so a failure part-way through
    # the writes below still leaves `restore` everything it needs.
    for key in sorted(writes):
        target = root / key
        if key in created:
            if _file_digest(target) in (None, hashes.get(key)):
                hashes[key] = digest(writes[key])  # still ours: track what this apply writes
            continue  # a file an earlier apply created has no original to keep
        if not target.exists():
            created.append(key)
            hashes[key] = digest(writes[key])
        elif backup:
            saved = f"{LINK_BACKUPS}/{key.lstrip('/')}" if key in aliases else key
            if not (backup_root / saved).exists():
                (backup_root / saved).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup_root / saved)
            if key in aliases:
                link_targets.setdefault(key, saved)
    for relative in sorted(remove_links):
        if (root / relative).is_symlink():
            removed.setdefault(relative, os.readlink(root / relative))
    if backup and (writes or remove_links):
        backup_root.mkdir(parents=True, exist_ok=True)
        record = {"created": created}
        if hashes:
            record["created_hashes"] = hashes
        if link_targets:
            record["symlink_targets"] = link_targets
        if removed:
            record["removed_links"] = removed
        (backup_root / MANIFEST).write_text(json.dumps(record, indent=2) + "\n")
    # Phase 2: the changes themselves.
    for key, text in sorted(writes.items()):
        scaffold.write_file(root / key, text, True, executable=key.endswith(".sh"))
    for relative in sorted(remove_links):
        link = root / relative
        if link.is_symlink():
            link.unlink()
        elif not backup and link.is_dir():
            shutil.rmtree(link)  # the preview copy holds a real folder where the project has a link


def _remove_empty_parents(root, folder):
    """Remove the folders an apply made for a file it created, up to (not including) the root."""
    while root in folder.parents:
        try:
            folder.rmdir()  # fails, and stops the walk, as soon as a folder still holds something
        except OSError:
            return
        folder = folder.parent


def _delete_created(root, manifest, outside, skipped, kept, discard_edits):
    hashes = manifest.get("created_hashes") or {}
    for relative in manifest.get("created", []):
        target = (root / str(relative)).resolve()
        if not target.is_file():
            continue
        recorded = hashes.get(str(relative))
        if recorded and not discard_edits and _file_digest(target) != recorded:
            kept.append(str(relative))  # edited since the apply: never destroy the user's work
            continue
        if _within(root, target):
            target.unlink()
            _remove_empty_parents(root, target.parent)
        elif outside and is_absolute(relative):
            target.unlink()
        else:
            skipped.append(str(relative))


def _restore_link_targets(root, backup_root, manifest, outside, restored, skipped):
    for key, saved in sorted((manifest.get("symlink_targets") or {}).items()):
        source = backup_root / str(saved)
        if not source.is_file() or not _within(backup_root.resolve(), source):
            continue
        target = root / str(key)
        allowed = _within(root, target) or (outside and is_absolute(key))
        if target.is_symlink() or not allowed:
            skipped.append(str(key))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        restored.append(str(key))


def _restore_links(root, manifest, outside, restored, skipped):
    for relative, target in sorted((manifest.get("removed_links") or {}).items()):
        link = root / str(relative)
        if is_absolute(relative) or not _within(root, link.parent) or link.exists() or link.is_symlink():
            continue
        if not (outside or _within(root, link.parent / str(target))):
            skipped.append(str(relative))  # a link that points out of the root is recreated only with --outside
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(target), link)
        restored.append(str(relative))


def restore(root, outside=False, discard_edits=False):
    """Undo every apply since the backup folder was created.

    Files outside the root are left alone, listed under "skipped", and their
    backups are kept, unless `outside` is true. A file an apply created is kept
    (listed under "kept_edited") when its content changed since, unless
    `discard_edits` is true.
    """
    backup_root = root / BACKUP_DIR
    if not backup_root.is_dir():
        raise scaffold.ScaffoldError(f"no {BACKUP_DIR}/ in {root}; nothing to restore")
    _refuse_links(backup_root)
    root = root.resolve()
    manifest = context_cost.load_json(backup_root / MANIFEST)
    restored, skipped, kept = [], [], []
    _delete_created(root, manifest, outside, skipped, kept, discard_edits)
    for saved in sorted(path for path in backup_root.rglob("*") if path.is_file()):
        relative = saved.relative_to(backup_root).as_posix()
        if relative == MANIFEST or relative.startswith(f"{LINK_BACKUPS}/"):
            continue
        target = root / relative
        if target.is_symlink() or not (outside or _within(root, target.parent)):
            skipped.append(relative)  # the path is now a link, or leads out of the root: do not write through it
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, target)
        restored.append(relative)
    _restore_link_targets(root, backup_root, manifest, outside, restored, skipped)
    _restore_links(root, manifest, outside, restored, skipped)
    if not skipped:
        shutil.rmtree(backup_root)
    return {"mode": "restored", "files": restored, "skipped": skipped, "kept_edited": kept}
