from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dkctf_anim_format import AnimFormatError, parse_anim


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    files = sorted(root.rglob("*.anim"))
    unique: dict[str, Path] = {}
    duplicate_paths: defaultdict[str, list[str]] = defaultdict(list)

    for path in files:
        digest = _sha256(path.read_bytes())
        unique.setdefault(digest, path)
        duplicate_paths[digest].append(_rel(path, root))

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for digest, path in sorted(unique.items(), key=lambda item: _rel(item[1], root)):
        try:
            anim = parse_anim(path, strict=True)
        except (OSError, AnimFormatError) as exc:
            errors.append({"path": _rel(path, root), "sha256": digest, "error": str(exc)})
            continue

        q = anim.root_transform.quaternion_wxyz
        t = anim.root_transform.translation_xyz
        used = anim.used_payload
        rows.append({
            "path": _rel(path, root),
            "sha256": digest,
            "duplicate_count": len(duplicate_paths[digest]),
            "file_size": len(anim.raw),
            "family": f"0x{anim.family:02X}",
            "family_flags": f"0x{anim.family_flags:02X}",
            "mode": anim.mode,
            "stored_frame_count": anim.stored_frame_count,
            "group_hash": f"0x{anim.group_hash:08X}",
            "descriptor_width": anim.descriptor.encoded_width,
            "descriptor_source_count": anim.descriptor.source_count,
            "descriptor_source_ids": ",".join(map(str, anim.descriptor.source_ids)),
            "root_q_w": q[0],
            "root_q_x": q[1],
            "root_q_y": q[2],
            "root_q_z": q[3],
            "root_q_norm_sq": anim.root_transform.quaternion_norm_sq,
            "root_t_x": t[0],
            "root_t_y": t[1],
            "root_t_z": t[2],
            "root_flags": f"0x{anim.root_flags:02X}",
            "payload_offset": anim.payload_offset,
            "payload_size": len(anim.payload),
            "used_payload_size": len(used),
            "zero_padding_size": anim.zero_padding_size,
            "payload_first_byte": f"0x{used[0]:02X}" if used else "",
            "payload_sha256": _sha256(used),
            "duplicate_paths": duplicate_paths[digest],
        })

    family_counts = Counter(row["family"] for row in rows)
    descriptor_counts = Counter(
        (row["descriptor_width"], row["descriptor_source_count"], row["descriptor_source_ids"])
        for row in rows
    )
    root_flag_counts = Counter(row["root_flags"] for row in rows)
    payload_first_byte_counts = Counter(row["payload_first_byte"] for row in rows)

    report: dict[str, Any] = {
        "format": "DKCTF_ANIM_CORPUS_AUDIT_V1",
        "root": str(root),
        "file_count": len(files),
        "unique_file_count": len(unique),
        "duplicate_file_count": len(files) - len(unique),
        "strict_parse_success_count": len(rows),
        "strict_parse_error_count": len(errors),
        "families": dict(sorted(family_counts.items())),
        "descriptors": [
            {
                "encoded_width": key[0],
                "source_count": key[1],
                "source_ids": key[2],
                "count": count,
            }
            for key, count in sorted(descriptor_counts.items())
        ],
        "root_flags": dict(sorted(root_flag_counts.items())),
        "payload_first_bytes": dict(sorted(payload_first_byte_counts.items())),
        "errors": errors,
        "verified_invariants": [
            "RFRM form size equals file_size - 0x20",
            "RFRM unknown u64 is zero",
            "form id is ANIM and both versions are 20",
            "payload tag is 0x49170014",
            "inner size equals file_size - 0x28",
            "families observed are 0x81, 0x82, 0xC1, and 0xC2",
            "C-family files insert one byte at 0x30 and move descriptor/payload by one byte",
            "descriptor encoded_width equals 7 * source_count",
            "descriptor separator is 0xFF and source ids are 1..source_count",
            "root quaternion WXYZ is normalized and is followed by translation XYZ",
        ],
        "not_decoded": [
            "compressed skeletal channel payload",
            "exact source-id semantics",
            "root_flags semantics",
            "key masks, per-track bit widths, quantization, and track-to-joint binding",
        ],
    }
    return report, rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    serializable: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        copy["duplicate_paths"] = ";".join(copy["duplicate_paths"])
        serializable.append(copy)
    if not serializable:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(serializable[0]))
        writer.writeheader()
        writer.writerows(serializable)


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict DKCTF ANIM corpus audit")
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path, default=Path("dkctf_anim_audit"))
    args = parser.parse_args()

    report, rows = audit(args.root)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (args.out / "files.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_csv(args.out / "files.csv", rows)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["strict_parse_error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
