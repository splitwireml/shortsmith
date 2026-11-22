"""Local media store with S3-style keys (S1).

One implementation, no interface class; an R2/S3 version with the same
five methods is a drop-in later. Keys look like `videos/3/clip_0.mp4`.
Any key that would land outside the media folder is refused.
"""

from pathlib import Path


class Storage:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _resolve(self, key: str) -> Path:
        # Resolve first, judge second: `videos/../../x` only shows its
        # true destination once the `..` parts are folded away.
        target = (self.root / key).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"That file name is not allowed: {key!r}")
        return target

    def _file(self, key: str) -> Path:
        if not key:
            raise ValueError("A file name is needed.")
        target = self._resolve(key)
        if target == self.root:
            raise ValueError(f"That file name is not allowed: {key!r}")
        return target

    def put(self, key: str, data: bytes) -> None:
        target = self._file(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def path(self, key: str) -> Path:
        return self._file(key)

    def exists(self, key: str) -> bool:
        return self._file(key).is_file()

    def delete(self, key: str) -> None:
        # Like S3, deleting a key that is not there is not an error.
        self._file(key).unlink(missing_ok=True)

    def list(self, prefix: str) -> list[str]:
        self._resolve(prefix)  # a prefix may not escape either
        if not self.root.is_dir():
            return []
        keys = [
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
            if p.is_file()
        ]
        return sorted(k for k in keys if k.startswith(prefix))

    def size(self, prefix: str) -> int:
        return sum(self._resolve(k).stat().st_size for k in self.list(prefix))
