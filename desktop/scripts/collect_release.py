"""归档同次原生发行包；不收集临时配置、证书或开发目录。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil


def collect(source: Path, destination: Path, target: str, revision: str) -> None:
    if target not in {"mac-arm64", "mac-x64", "win-x64"}:
        raise ValueError("未知发行目标")
    required = {".dmg", ".zip"} if target.startswith("mac-") else {".exe"}
    manifest = "latest-mac.yml" if target.startswith("mac-") else "latest.yml"
    artifacts = sorted(p for p in source.iterdir() if p.is_file() and (
        p.suffix in required or p.name.endswith(".blockmap") or p.name == manifest
    ))
    for suffix in required:
        if sum(p.suffix == suffix for p in artifacts) != 1:
            raise ValueError(f"必须恰有一个 {suffix} 发行包")
    if not any(p.name == manifest for p in artifacts):
        raise ValueError("缺少更新清单")
    # 独立输出目录必须为空，防止把旧版本文件一起交给发布负责人。
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("发行归档目录必须为空")
    checksums = []
    for artifact in artifacts:
        with artifact.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        shutil.copy2(artifact, destination / artifact.name)
        checksums.append(f"{digest}  {artifact.name}\n")
    (destination / "SHA256SUMS.txt").write_text("".join(checksums), encoding="utf-8")
    (destination / "build-info.json").write_text(json.dumps(
        {"target": target, "revision": revision}, ensure_ascii=False, indent=2
    ) + "\n", encoding="utf-8")


if __name__ == "__main__":
    desktop = Path(__file__).resolve().parents[1]
    collect(desktop / "build/electron", desktop / "build/release",
            os.environ["RELEASE_TARGET"], os.environ["GITHUB_SHA"])
