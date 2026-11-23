"""Join clips into one vertical MP4 at the recipe's video size, with ffmpeg.

Every clip is scaled and padded to the same frame, then joined with the
concat filter so clips from separate calls (possibly different sizes)
still join cleanly. Clips carry their own audio; it is kept.

`run_ffmpeg` lives here too: practice media in `media.py` runs ffmpeg
the same way, with the same plain-language failures.
"""

import subprocess
from pathlib import Path


def run_ffmpeg(args: list[str], what: str) -> None:
    """Run ffmpeg quietly, overwriting. `args` excludes the binary itself."""
    try:
        done = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True
        )
    except FileNotFoundError:
        raise RuntimeError("ffmpeg was not found. Install it, then press Retry.") from None
    if done.returncode != 0:
        detail = (done.stderr or "").strip().splitlines()
        raise RuntimeError(f"{what} failed. {detail[-1] if detail else 'Press Retry to try again.'}")


# Width × height of the vertical frame for each video size.
FRAME_SIZES = {"360p": (360, 640), "720p": (720, 1280), "1080p": (1080, 1920), "4k": (2160, 3840)}


def stitch(clip_paths: list[Path], output_path: Path, resolution: str = "1080p") -> None:
    if not clip_paths:
        raise RuntimeError("There are no clips to join together yet.")
    w, h = FRAME_SIZES[resolution]
    frame = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
    )
    parts = []
    joined = ""
    for i in range(len(clip_paths)):
        parts.append(f"[{i}:v]{frame}[v{i}]")
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        joined += f"[v{i}][a{i}]"
    parts.append(f"{joined}concat=n={len(clip_paths)}:v=1:a=1[v][a]")
    args: list[str] = []
    for path in clip_paths:
        args += ["-i", str(path)]
    args += [
        "-filter_complex", ";".join(parts),
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        str(output_path),
    ]
    run_ffmpeg(args, "Joining the clips together")
