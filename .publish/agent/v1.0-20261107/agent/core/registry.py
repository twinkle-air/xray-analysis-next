"""Frozen model registry: version, entrypoint, dependency hashes and declared scope.

The agent never lets a prompt change a model version, entrypoint or element set.
"""
from __future__ import annotations
import hashlib, json, pathlib
from .paths import read_json, Workspace


class RegistryError(Exception):
    pass


class ModelRegistry:
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self._data = read_json(workspace.model_registry())
        self._integrity_cache: dict[str, dict] = {}

    @property
    def default_model(self) -> str:
        return self._data["default_model"]

    @property
    def schema_version(self) -> str:
        return self._data["schema_version"]

    def models(self) -> dict:
        return dict(self._data["models"])

    def model(self, version: str) -> dict:
        models = self._data["models"]
        if version not in models:
            raise RegistryError(f"unknown model {version!r}; allowed: {sorted(models)}")
        return dict(models[version])

    def adapter(self) -> dict:
        return dict(self._data["adapter"])

    def verify_package(self, version: str) -> dict:
        """Check every file the model lists in its freeze.json against the manifest.

        The frozen entrypoint checks local_files and processing_dependencies on import;
        a cache hit never executes it, so an install whose dependencies changed would
        otherwise keep serving a stale result. Both sections are checked here with the
        same口径. Older freeze formats (a bare `files` map) are honored as-is.

        Returns {ok, checked, mismatches}. Does NOT recompute a hash to 'fix' a mismatch.
        """
        model = self.model(version)
        integrity_file = self.workspace.root / model["integrity_file"]
        if not integrity_file.exists():
            raise RegistryError(f"integrity file missing for {version}: {integrity_file}")
        freeze = read_json(integrity_file)
        root = self.workspace.root / model["package_root"]
        # the entrypoint verifies local_files and processing_dependencies; a bare
        # `files` map is the older format and is checked the same way.
        files = freeze.get("local_files") or freeze.get("files") or {}
        processing = freeze.get("processing_dependencies", {})
        mismatches = []
        checked = 0
        for rel, expected in files.items():
            checked += 1
            path = root / rel
            if not path.exists():
                mismatches.append((rel, expected, "missing"))
                continue
            actual = hashlib.file_digest(open(path, "rb"), "sha256").hexdigest()
            if actual != expected:
                mismatches.append((rel, expected, actual))
        for rel, expected in processing.items():
            checked += 1
            path = (root / rel).resolve()
            if not path.exists():
                mismatches.append((rel, expected, "missing"))
                continue
            actual = hashlib.file_digest(open(path, "rb"), "sha256").hexdigest()
            if actual != expected:
                mismatches.append((rel, expected, actual))
        return {"version": version, "ok": not mismatches, "checked": checked,
                "mismatches": mismatches, "integrity_file": str(integrity_file)}

    def package_sha(self, version: str) -> str:
        """Stable fingerprint of the whole package, derived from the manifest itself."""
        model = self.model(version)
        manifest = self.workspace.root / model["package_sha256_source"]
        return sha256_of_file(manifest)


def sha256_of_file(path: pathlib.Path) -> str:
    import hashlib

    return hashlib.file_digest(open(path, "rb"), "sha256").hexdigest()