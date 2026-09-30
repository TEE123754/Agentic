"""Fetch pinned free runtime/model assets; setup only, never used during audit runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "FrictionLab-phase0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def metadata():
    release = get_json("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest")
    assets = [a for a in release["assets"] if "win-cpu-x64" in a["name"] and a["name"].endswith(".zip")]
    if not assets:
        releases = get_json("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10")
        for candidate in releases:
            assets = [a for a in candidate["assets"] if "win-cpu-x64" in a["name"] and a["name"].endswith(".zip")]
            if assets:
                release = candidate
                break
    if len(assets) != 1:
        raise RuntimeError(f"Expected one Windows CPU asset, found: {[a['name'] for a in assets]}")
    model = get_json("https://huggingface.co/api/models/Qwen/Qwen3-4B-GGUF?blobs=true")
    filename = next(
        s["rfilename"] for s in model["siblings"]
        if s["rfilename"].lower() == "qwen3-4b-q4_k_m.gguf"
    )
    blob = next(s for s in model["siblings"] if s["rfilename"] == filename)
    return {
        "runtime": {
            "release": release["tag_name"], "asset": assets[0]["name"],
            "url": assets[0]["browser_download_url"], "size": assets[0]["size"],
            "expected_digest": assets[0].get("digest"),
            "repository": "https://github.com/ggml-org/llama.cpp", "license": "MIT",
        },
        "model": {
            "repository": "Qwen/Qwen3-4B-GGUF", "revision": model["sha"],
            "filename": filename, "size": blob.get("size"),
            "expected_sha256": blob.get("lfs", {}).get("sha256"),
            "url": f"https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/{model['sha']}/{filename}",
            "license": model.get("cardData", {}).get("license"),
        },
    }


def download(url: str, path: Path, expected_sha256: str | None):
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    if not path.exists():
        print(f"Downloading {path.name}", flush=True)
        digest = hashlib.sha256()
        downloaded = 0
        last_print = 0
        request = urllib.request.Request(url, headers={"User-Agent": "FrictionLab-phase0"})
        with urllib.request.urlopen(request, timeout=120) as source, partial.open("wb") as dest:
            while chunk := source.read(4 * 1024 * 1024):
                downloaded += len(chunk)
                if downloaded > 4 * 1024**3:
                    raise RuntimeError("Asset exceeds 4 GiB setup limit")
                dest.write(chunk)
                digest.update(chunk)
                if downloaded - last_print >= 256 * 1024**2:
                    print(f"  {downloaded // 1024**2} MiB received", flush=True)
                    last_print = downloaded
        checksum = digest.hexdigest()
        if expected_sha256 and checksum != expected_sha256:
            raise RuntimeError(f"Checksum mismatch for {path.name}")
        partial.replace(path)
    else:
        with path.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        if expected_sha256 and checksum != expected_sha256:
            raise RuntimeError(f"Checksum mismatch for existing {path.name}")
    return checksum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    manifest_path = ROOT / "configs" / "resource-manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else metadata()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.download:
        runtime_key = "runtime" if os.name == "nt" else "runtime_linux"
        runtime, model = manifest[runtime_key], manifest["model"]
        archive = ROOT / ".runtime" / runtime["asset"]
        expected = runtime.get("expected_digest")
        runtime["sha256"] = download(
            runtime["url"], archive, expected.removeprefix("sha256:") if expected else None
        )
        target = (ROOT / ".runtime" / "llama").resolve()
        target.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            with zipfile.ZipFile(archive) as bundle:
                for entry in bundle.infolist():
                    resolved = (target / entry.filename).resolve()
                    if not resolved.is_relative_to(target):
                        raise RuntimeError("Unsafe archive path")
                bundle.extractall(target)
            server = next(target.rglob("llama-server.exe"))
        else:
            with tarfile.open(archive, "r:gz") as bundle:
                for entry in bundle.getmembers():
                    resolved = (target / entry.name).resolve()
                    if not resolved.is_relative_to(target) or not (entry.isfile() or entry.isdir()):
                        raise RuntimeError("Unsafe archive member")
                bundle.extractall(target, filter="data")
            server = next(target.rglob("llama-server"))
            server.chmod(server.stat().st_mode | 0o111)
        model_path = ROOT / "models" / model["filename"]
        model["sha256"] = download(model["url"], model_path, model.get("expected_sha256"))
        runtime["local_path"] = str(server.relative_to(ROOT))
        model["local_path"] = str(model_path.relative_to(ROOT))
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        config_path = ROOT / "configs" / "models.json"
        config = json.loads(config_path.read_text())
        config["planner"]["revision"] = model["revision"]
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
