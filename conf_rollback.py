#!/usr/bin/env python3
"""
conf_rollback.py

A minimal configuration backup & restore tool.
Saves JSON configs before changes, supports listing, inspect, verify, restore, and prune.

Usage examples:
  Save a backup:
    python conf_rollback.py save /etc/myapp/config.json --note "before enabling X"

  List backups:
    python conf_rollback.py list

  Show backup details:
    python conf_rollback.py show <backup_id>

  Restore a backup to original path:
    python conf_rollback.py restore <backup_id>

  Restore to a custom path:
    python conf_rollback.py restore <backup_id> --dest ./restored-config.json

  Verify checksums:
    python conf_rollback.py verify <backup_id>

  Prune older than N (keep latest N):
    python conf_rollback.py prune --keep 5
"""

from __future__ import annotations
import argparse
import json
import os
import shutil
import hashlib
import uuid
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Default backup storage dir (hidden in user's home, but you can change it)
DEFAULT_STORAGE_DIR = Path.home() / ".conf_backups"

INDEX_FILENAME = "backups_index.json"


def ensure_storage_dir(base_dir: Path = DEFAULT_STORAGE_DIR) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    index_path = base_dir / INDEX_FILENAME
    if not index_path.exists():
        index_path.write_text(json.dumps({"backups": []}, indent=2), encoding="utf-8")
    return base_dir


def load_index(base_dir: Path = DEFAULT_STORAGE_DIR) -> Dict[str, Any]:
    index_path = base_dir / INDEX_FILENAME
    try:
        with index_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Recover from corrupted index by recreating a fresh index (warn)
        print(f"Warning: index file {index_path} is corrupted. Recreating.")
        index_path.write_text(json.dumps({"backups": []}, indent=2), encoding="utf-8")
        return {"backups": []}


def save_index(index: Dict[str, Any], base_dir: Path = DEFAULT_STORAGE_DIR) -> None:
    index_path = base_dir / INDEX_FILENAME
    tmp = index_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, index_path)


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_bytes(dest: Path, data: bytes) -> None:
    tmp = dest.with_suffix(".tmp")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, dest)


def save_backup(src_path: Path, note: Optional[str], base_dir: Path = DEFAULT_STORAGE_DIR) -> Dict[str, Any]:
    if not src_path.exists():
        raise FileNotFoundError(f"Source file does not exist: {src_path}")

    # validate JSON
    try:
        with src_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise ValueError(f"Failed to read JSON from {src_path}: {e}")

    base_dir = ensure_storage_dir(base_dir)
    index = load_index(base_dir)

    # create backup id and filename
    backup_id = uuid.uuid4().hex
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    ext = src_path.suffix or ".json"
    backup_filename = f"{backup_id}{ext}"
    backup_path = base_dir / backup_filename

    # write backup atomically
    raw_text = json.dumps(data, indent=2).encode("utf-8")
    atomic_write_bytes(backup_path, raw_text)

    checksum = compute_sha256(backup_path)

    entry = {
        "id": backup_id,
        "timestamp": timestamp,
        "original_path": str(src_path.resolve()),
        "backup_filename": backup_filename,
        "checksum": checksum,
        "note": note or "",
    }

    index["backups"].append(entry)
    save_index(index, base_dir)

    return entry


def list_backups(base_dir: Path = DEFAULT_STORAGE_DIR, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    base_dir = ensure_storage_dir(base_dir)
    index = load_index(base_dir)
    backups = sorted(index.get("backups", []), key=lambda b: b.get("timestamp", ""), reverse=True)
    if limit is not None:
        backups = backups[:limit]
    return backups


def get_backup_by_id(backup_id: str, base_dir: Path = DEFAULT_STORAGE_DIR) -> Optional[Dict[str, Any]]:
    index = load_index(base_dir)
    for b in index.get("backups", []):
        if b.get("id") == backup_id:
            return b
    return None


def show_backup(backup_id: str, base_dir: Path = DEFAULT_STORAGE_DIR) -> Dict[str, Any]:
    b = get_backup_by_id(backup_id, base_dir)
    if not b:
        raise KeyError(f"No backup with id {backup_id}")
    # load content
    backup_path = base_dir / b["backup_filename"]
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file missing: {backup_path}")
    with backup_path.open("r", encoding="utf-8") as f:
        content = json.load(f)
    return {"metadata": b, "content": content}


def verify_backup(backup_id: str, base_dir: Path = DEFAULT_STORAGE_DIR) -> bool:
    b = get_backup_by_id(backup_id, base_dir)
    if not b:
        raise KeyError(f"No backup with id {backup_id}")
    path = base_dir / b["backup_filename"]
    if not path.exists():
        raise FileNotFoundError(f"Backup file missing: {path}")
    current_checksum = compute_sha256(path)
    return current_checksum == b.get("checksum")


def restore_backup(backup_id: str, dest: Optional[Path] = None, base_dir: Path = DEFAULT_STORAGE_DIR, force: bool = False) -> Path:
    b = get_backup_by_id(backup_id, base_dir)
    if not b:
        raise KeyError(f"No backup with id {backup_id}")

    base_dir = ensure_storage_dir(base_dir)
    backup_path = base_dir / b["backup_filename"]
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file missing: {backup_path}")

    # determine destination
    if dest is None:
        dest = Path(b["original_path"])
    else:
        dest = dest

    # if destination exists and not force, create a backup of it first
    if dest.exists() and not force:
        # save current dest as a pre-restore backup to avoid data loss
        pre_note = f"pre-restore of {dest} from restore-id {backup_id}"
        pre_entry = save_backup(dest, note=pre_note, base_dir=base_dir)
        print(f"Existing destination backed up as {pre_entry['id']} before restoring (pre-restore).")

    # load backup content and write atomically to destination
    with backup_path.open("rb") as f:
        data = f.read()

    # Ensure destination directory exists
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Write atomically
    atomic_write_bytes(dest, data)

    return dest


def prune_keep_n(keep: int, base_dir: Path = DEFAULT_STORAGE_DIR) -> List[str]:
    if keep <= 0:
        raise ValueError("keep must be > 0")

    base_dir = ensure_storage_dir(base_dir)
    index = load_index(base_dir)
    backups = sorted(index.get("backups", []), key=lambda b: b.get("timestamp", ""), reverse=True)
    to_remove = backups[keep:]
    removed_ids = []
    for entry in to_remove:
        fname = base_dir / entry["backup_filename"]
        try:
            if fname.exists():
                fname.unlink()
        except Exception as e:
            print(f"Warning: failed to remove backup file {fname}: {e}")
        removed_ids.append(entry["id"])

    # keep only the first `keep` entries
    index["backups"] = backups[:keep]
    save_index(index, base_dir)
    return removed_ids


def prune_older_than(days: int, base_dir: Path = DEFAULT_STORAGE_DIR) -> List[str]:
    if days <= 0:
        raise ValueError("days must be > 0")
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    base_dir = ensure_storage_dir(base_dir)
    index = load_index(base_dir)
    remaining = []
    removed = []
    for entry in index.get("backups", []):
        ts = entry.get("timestamp")
        try:
            t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            t = None
        if t is None or t < cutoff:
            # remove file
            fname = base_dir / entry["backup_filename"]
            try:
                if fname.exists():
                    fname.unlink()
            except Exception as e:
                print(f"Warning: failed to remove backup {fname}: {e}")
            removed.append(entry["id"])
        else:
            remaining.append(entry)
    index["backups"] = remaining
    save_index(index, base_dir)
    return removed


def parse_args():
    p = argparse.ArgumentParser(description="Simple JSON Configuration Backup & Restore Tool")
    p.add_argument("--storage", "-s", type=Path, default=DEFAULT_STORAGE_DIR, help="Backup storage directory (default: ~/.conf_backups)")
    sub = p.add_subparsers(dest="cmd", required=True)

    save_p = sub.add_parser("save", help="Save a backup of a JSON file")
    save_p.add_argument("src", type=Path, help="Source JSON file to backup")
    save_p.add_argument("--note", "-n", type=str, help="Optional note for this backup")

    list_p = sub.add_parser("list", help="List backups")
    list_p.add_argument("--limit", "-l", type=int, default=None, help="Limit how many recent backups to list")

    show_p = sub.add_parser("show", help="Show metadata and content of a backup")
    show_p.add_argument("id", help="Backup id to show")

    verify_p = sub.add_parser("verify", help="Verify checksum of a backup")
    verify_p.add_argument("id", help="Backup id to verify")

    restore_p = sub.add_parser("restore", help="Restore a backup to its original path (or custom dest)")
    restore_p.add_argument("id", help="Backup id to restore")
    restore_p.add_argument("--dest", "-d", type=Path, default=None, help="Destination path to restore to (default: original path saved in metadata)")
    restore_p.add_argument("--force", "-f", action="store_true", help="Force overwrite without pre-backup of destination")

    prune_p = sub.add_parser("prune", help="Prune old backups")
    prune_group = prune_p.add_mutually_exclusive_group(required=True)
    prune_group.add_argument("--keep", type=int, help="Keep latest N backups and remove the rest")
    prune_group.add_argument("--older-than", type=int, help="Remove backups older than N days")

    return p.parse_args()


def main():
    args = parse_args()
    base_dir = args.storage
    ensure_storage_dir(base_dir)

    try:
        if args.cmd == "save":
            entry = save_backup(args.src, args.note, base_dir)
            print("Backup saved:")
            print(json.dumps(entry, indent=2))

        elif args.cmd == "list":
            backups = list_backups(base_dir, limit=args.limit)
            if not backups:
                print("No backups found.")
                return
            for b in backups:
                ts = b.get("timestamp", "")
                oid = b.get("id")
                orig = b.get("original_path", "")
                note = b.get("note", "")
                print(f"- id: {oid}  time: {ts}  file: {Path(orig).name}  note: {note}")

        elif args.cmd == "show":
            data = show_backup(args.id, base_dir)
            print("Metadata:")
            print(json.dumps(data["metadata"], indent=2))
            print("\nContent:")
            pretty = json.dumps(data["content"], indent=2)
            print(pretty)

        elif args.cmd == "verify":
            ok = verify_backup(args.id, base_dir)
            print("OK" if ok else "CORRUPT")

        elif args.cmd == "restore":
            dest = args.dest if args.dest is not None else None
            restored = restore_backup(args.id, dest=dest, base_dir=base_dir, force=args.force)
            print(f"Restored backup {args.id} -> {restored}")

        elif args.cmd == "prune":
            if args.keep is not None:
                removed = prune_keep_n(args.keep, base_dir)
                print(f"Removed backups: {removed}")
            else:
                removed = prune_older_than(args.older_than, base_dir)
                print(f"Removed backups: {removed}")

        else:
            print("Unknown command. Use --help for usage.")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
