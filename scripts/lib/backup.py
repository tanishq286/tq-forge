"""Backup, apply and restore for the context optimizer (Python stdlib only).

Every `--apply` goes through `apply_writes`, which keeps what `restore` needs
in <root>/.tq-forge-backup/:

  <path>                    the original of each file that was changed
  symlink-targets/<path>    the original of a file reached through a symlink
  manifest.json             {"created": [...],          files to delete on restore
                             "symlink_targets": {...},  file -> its backup
                             "removed_links": {...}}    symlink -> where it pointed

The first backup of a file wins, so `restore` always goes back to the state
before the first apply, however many applies followed.

`restore` trusts the manifest only inside the root. A file outside it (the
target of a followed symlink) is restored only with `outside=True`, so a
backup folder that arrived with a cloned project cannot make `restore` write
or delete somewhere else on the machine.
"""

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
    """True when `path` is `folder` or sits under it, after resolving symlinks."""
    resolved = path.resolve()
    return resolved == folder or folder in resolved.parents


def apply_writes(root, writes, backup=True, aliases=None, remove_links=None):
    """Write a plan into `root`. `backup=False` is the preview run on a scratch copy."""
    aliases, remove_links = aliases or {}, remove_links or {}
    backup_root = root / BACKUP_DIR
    manifest = context_cost.load_json(backup_root / MANIFEST)
    created = list(manifest.get("created", []))
    link_targets = dict(manifest.get("symlink_targets") or {})
    removed = dict(manifest.get("removed_links") or {})
    for key, text in sorted(writes.items()):
        target = root / key
        if key in created:
            pass  # a file an earlier apply created has no original to keep
        elif not target.exists():
            created.append(key)
        elif backup:
            saved = f"{LINK_BACKUPS}/{key.lstrip('/')}" if key in aliases else key
            if not (backup_root / saved).exists():
                (backup_root / saved).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup_root / saved)
            if key in aliases:
                link_targets.setdefault(key, saved)
        scaffold.write_file(target, text, True, executable=key.endswith(".sh"))
    for relative in sorted(remove_links):
        link = root / relative
        if link.is_symlink():
            removed.setdefault(relative, os.readlink(link))
            link.unlink()
        elif not backup and link.is_dir():
            shutil.rmtree(link)  # the preview copy holds a real folder where the project has a link
    if backup and (writes or remove_links):
        backup_root.mkdir(parents=True, exist_ok=True)
        record = {"created": created}
        if link_targets:
            record["symlink_targets"] = link_targets
        if removed:
            record["removed_links"] = removed
        (backup_root / MANIFEST).write_text(json.dumps(record, indent=2) + "\n")


def _remove_empty_parents(root, folder):
    """Remove the folders an apply made for a file it created, up to (not including) the root."""
    while root in folder.parents:
        try:
            folder.rmdir()  # fails, and stops the walk, as soon as a folder still holds something
        except OSError:
            return
        folder = folder.parent


def _delete_created(root, manifest, outside, skipped):
    for relative in manifest.get("created", []):
        target = (root / str(relative)).resolve()
        if not target.is_file():
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
        if not (outside or _within(root, target)):
            skipped.append(str(key))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        restored.append(str(key))


def _restore_links(root, manifest, restored):
    for relative, target in sorted((manifest.get("removed_links") or {}).items()):
        link = root / str(relative)
        if is_absolute(relative) or not _within(root, link.parent) or link.exists() or link.is_symlink():
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(target), link)
        restored.append(str(relative))


def restore(root, outside=False):
    """Undo every apply since the backup folder was created.

    Files outside the root are left alone, listed under "skipped", and their
    backups are kept, unless `outside` is true.
    """
    backup_root = root / BACKUP_DIR
    if not backup_root.is_dir():
        raise scaffold.ScaffoldError(f"no {BACKUP_DIR}/ in {root}; nothing to restore")
    root = root.resolve()
    manifest = context_cost.load_json(backup_root / MANIFEST)
    restored, skipped = [], []
    _delete_created(root, manifest, outside, skipped)
    for saved in sorted(path for path in backup_root.rglob("*") if path.is_file()):
        relative = saved.relative_to(backup_root).as_posix()
        if relative == MANIFEST or relative.startswith(f"{LINK_BACKUPS}/"):
            continue
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, root / relative)
        restored.append(relative)
    _restore_link_targets(root, backup_root, manifest, outside, restored, skipped)
    _restore_links(root, manifest, restored)
    if not skipped:
        shutil.rmtree(backup_root)
    return {"mode": "restored", "files": restored, "skipped": skipped}
