from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFilter
from rembg import new_session, remove


DEFAULT_MODEL = "u2net_human_seg"
DEFAULT_BACKEND = "rvm"
DEFAULT_CODEC = "prores"
DEFAULT_MAX_WIDTH = 0
DEFAULT_SHRINK = 1
DEFAULT_BLUR = 1.0
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".m4v", ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".flv", ".f4v"}
RVM_MODEL_DIR = Path(r"C:\dev\tools\_models\remove-portrait")
RVM_REPO = RVM_MODEL_DIR / "RobustVideoMatting"
RVM_WEIGHTS = RVM_MODEL_DIR / "rvm_mobilenetv3.pth"


def preload_onnxruntime_gpu_dlls() -> None:
    try:
        import onnxruntime as ort
    except Exception:
        return

    preload = getattr(ort, "preload_dlls", None)
    if preload is None:
        return

    try:
        preload(cuda=True, cudnn=True, msvc=True)
    except Exception as error:
        print(f"Warning: ONNX Runtime GPU DLL preload failed: {error}", file=sys.stderr)


def find_ffmpeg() -> Path:
    exe_dir = Path(__file__).resolve().parents[2]
    candidates = [
        Path(r"C:\dev\tools\ffmpeg.exe"),
        exe_dir / "ffmpeg.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    found = shutil.which("ffmpeg")
    if found:
        return Path(found)

    raise FileNotFoundError("ffmpeg.exe was not found. Put it in C:\\dev\\tools or on PATH.")


def build_default_output_path(input_path: Path, max_width: int, suffix: str = "_portrait_removed") -> Path:
    width_part = f"_{max_width}w" if max_width > 0 else ""
    candidate = input_path.with_name(f"{input_path.stem}{suffix}{width_part}.mov")
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        numbered = input_path.with_name(f"{input_path.stem}{suffix}{width_part}_{counter}.mov")
        if not numbered.exists():
            return numbered
        counter += 1


def build_preview_output_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_preview.mp4")


def normalize_model(model: str) -> str:
    value = model.strip() if model else DEFAULT_MODEL
    allowed = {"u2net_human_seg", "isnet-general-use", "birefnet-portrait"}
    if value not in allowed:
        raise ValueError(f"Unsupported model: {model}. Choose one of: {', '.join(sorted(allowed))}")
    return value


def get_session_providers(session) -> list[str]:
    inner_session = getattr(session, "inner_session", None)
    if inner_session is None:
        return []

    get_providers = getattr(inner_session, "get_providers", None)
    if get_providers is None:
        return []

    return list(get_providers())


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def apply_alpha_tuning(image: Image.Image, shrink: int, blur: float) -> Image.Image:
    rgba = image.convert("RGBA")
    if shrink <= 0 and blur <= 0:
        return rgba

    red, green, blue, alpha = rgba.split()
    if shrink > 0:
        alpha = alpha.filter(ImageFilter.MinFilter(shrink * 2 + 1))
    if blur > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(blur))
    return Image.merge("RGBA", (red, green, blue, alpha))


def checkerboard(size: tuple[int, int], tile: int = 24) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, "#f2f2f2")
    draw = ImageDraw.Draw(image)
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                draw.rectangle([x, y, x + tile - 1, y + tile - 1], fill="#cfcfcf")
    return image


def build_alpha_mov_command(ffmpeg: Path, frame_pattern: Path, input_path: Path, output_path: Path, fps: float, include_audio: bool) -> list[str]:
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-framerate",
        f"{fps}",
        "-i",
        str(frame_pattern),
    ]
    if include_audio:
        command.extend(["-i", str(input_path), "-map", "0:v", "-map", "1:a?", "-c:a", "copy", "-shortest"])
    command.extend(["-c:v", "qtrle", "-pix_fmt", "argb", str(output_path)])
    return command


def build_preview_command(ffmpeg: Path, frame_pattern: Path, output_path: Path, fps: float) -> list[str]:
    return [
        str(ffmpeg),
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-framerate",
        f"{fps}",
        "-i",
        str(frame_pattern),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]


def build_raw_alpha_mov_command(
    ffmpeg: Path,
    width: int,
    height: int,
    fps: float,
    input_path: Path,
    output_path: Path,
    include_audio: bool,
    codec: str,
    duration_seconds: float | None = None,
) -> list[str]:
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps}",
        "-i",
        "pipe:0",
    ]
    if include_audio:
        command.extend(["-i", str(input_path), "-map", "0:v", "-map", "1:a?", "-c:a", "copy", "-shortest"])
    if duration_seconds is not None:
        command.extend(["-t", f"{duration_seconds:.6f}"])

    if codec == "qtrle":
        command.extend(["-c:v", "qtrle", "-pix_fmt", "argb"])
    elif codec == "prores":
        command.extend(["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", "-qscale:v", "9"])
    else:
        raise ValueError(f"Unsupported alpha codec: {codec}")

    command.append(str(output_path))
    return command


def write_checker_preview_frames(frame_dir: Path, preview_dir: Path) -> None:
    if preview_dir.exists():
        shutil.rmtree(preview_dir)
    preview_dir.mkdir(parents=True)

    for frame in sorted(frame_dir.glob("*.png")):
        cutout = Image.open(frame).convert("RGBA")
        preview = checkerboard(cutout.size)
        preview.paste(cutout, mask=cutout.split()[-1])
        preview.save(preview_dir / frame.name)


def process_frames(
    input_path: Path,
    frame_dir: Path,
    model: str,
    max_width: int,
    shrink: int,
    blur: float,
    limit_seconds: float | None,
    alpha_matting: bool,
) -> tuple[int, float]:
    session = new_session(model)
    providers = get_session_providers(session)
    if providers:
        print(f"Providers: {', '.join(providers)}")
    else:
        print("Providers: unknown")

    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {input_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30
    source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if not width or not height:
        raise RuntimeError("Could not read video dimensions.")

    scale = min(1.0, max_width / width) if max_width > 0 else 1.0
    target = (int(width * scale), int(height * scale)) if scale < 1 else None
    frame_limit = int(round(fps * limit_seconds)) if limit_seconds else None
    total_frames = frame_limit if frame_limit is not None else source_frame_count
    if source_frame_count and total_frames:
        total_frames = min(total_frames, source_frame_count)
    output_width, output_height = target if target else (width, height)

    print(f"Input size:  {width}x{height} @ {fps:.2f}fps")
    print(f"Output size: {output_width}x{output_height}")
    if total_frames:
        print(f"Frames: {total_frames}")

    frame_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    count = 0
    last_progress_at = started

    while frame_limit is None or count < frame_limit:
        ok, frame = capture.read()
        if not ok:
            break
        if target:
            frame = cv2.resize(frame, target, interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        cutout = remove(
            Image.fromarray(rgb).convert("RGBA"),
            session=session,
            alpha_matting=alpha_matting,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10,
        )
        apply_alpha_tuning(cutout, shrink=shrink, blur=blur).save(frame_dir / f"{count + 1:06d}.png")
        count += 1
        now = time.perf_counter()
        if count == 1 or count % 30 == 0 or now - last_progress_at >= 5 or (total_frames and count >= total_frames):
            elapsed = time.perf_counter() - started
            seconds_per_frame = elapsed / count
            if total_frames:
                percent = min(100.0, (count / total_frames) * 100)
                remaining = max(0, total_frames - count) * seconds_per_frame
                print(
                    f"Processed {count}/{total_frames} frames "
                    f"({percent:.1f}%, {seconds_per_frame:.2f}s/frame, "
                    f"elapsed {format_duration(elapsed)}, eta {format_duration(remaining)})"
                )
            else:
                print(
                    f"Processed {count} frames "
                    f"({seconds_per_frame:.2f}s/frame, elapsed {format_duration(elapsed)})"
                )
            last_progress_at = now

    capture.release()
    return count, fps


def ensure_rvm_available() -> None:
    if not RVM_REPO.exists() or not RVM_WEIGHTS.exists():
        raise RuntimeError(
            "RobustVideoMatting files are missing. Run tools\\remove-portrait\\deps.ps1 first."
        )


def load_rvm_model(device, dtype):
    ensure_rvm_available()
    sys.path.insert(0, str(RVM_REPO))
    from model import MattingNetwork
    import torch

    model = MattingNetwork("mobilenetv3").eval().to(device=device, dtype=dtype)
    state = torch.load(RVM_WEIGHTS, map_location=device)
    model.load_state_dict(state)
    return model


def rvm_frames_to_tensor(frames_bgr, device, dtype):
    import numpy as np
    import torch

    frames_rgb = [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in frames_bgr]
    array = np.stack(frames_rgb, axis=0)
    tensor = torch.from_numpy(array).to(device=device)
    return tensor.permute(0, 3, 1, 2).unsqueeze(0).to(dtype=dtype).div_(255)


def rvm_frame_to_rgba(frame_bgr, pha, index: int) -> bytes:
    import numpy as np

    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    alpha = pha[0, index, 0].mul(255).byte().contiguous().cpu().numpy()
    rgba = np.dstack([rgb, alpha])
    return rgba.tobytes()


def process_rvm_video(
    input_path: Path,
    output_path: Path,
    ffmpeg: Path,
    max_width: int,
    limit_seconds: float | None,
    include_audio: bool,
    downsample_ratio: float,
    chunk_size: int,
    codec: str,
) -> int:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("RVM backend needs CUDA, but torch.cuda.is_available() is false.")

    device = torch.device("cuda")
    dtype = torch.float16
    model = load_rvm_model(device, dtype)

    capture = cv2.VideoCapture(str(input_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {input_path}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30
    source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if not width or not height:
        raise RuntimeError("Could not read video dimensions.")

    scale = min(1.0, max_width / width) if max_width > 0 else 1.0
    output_width, output_height = (int(width * scale), int(height * scale)) if scale < 1 else (width, height)
    frame_limit = int(round(fps * limit_seconds)) if limit_seconds else None
    total_frames = frame_limit if frame_limit is not None else source_frame_count
    if source_frame_count and total_frames:
        total_frames = min(total_frames, source_frame_count)

    print("Backend: RVM")
    print(f"Device:  {torch.cuda.get_device_name(0)}")
    print(f"Dtype:   {dtype}")
    print(f"Ratio:   {downsample_ratio}")
    print(f"Chunk:   {chunk_size}")
    print(f"Codec:   {codec}")
    print(f"Input size:  {width}x{height} @ {fps:.2f}fps")
    print(f"Output size: {output_width}x{output_height}")
    if total_frames:
        print(f"Frames: {total_frames}")

    output_duration = total_frames / fps if total_frames else None
    command = build_raw_alpha_mov_command(
        ffmpeg,
        output_width,
        output_height,
        fps,
        input_path,
        output_path,
        include_audio,
        codec,
        output_duration,
    )
    writer = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert writer.stdin is not None

    rec = [None] * 4
    started = time.perf_counter()
    count = 0
    last_progress_at = started

    try:
        with torch.inference_mode():
            while frame_limit is None or count < frame_limit:
                frames = []
                while len(frames) < chunk_size and (frame_limit is None or count + len(frames) < frame_limit):
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if scale < 1:
                        frame = cv2.resize(frame, (output_width, output_height), interpolation=cv2.INTER_AREA)
                    frames.append(frame)

                if not frames:
                    break

                src = rvm_frames_to_tensor(frames, device, dtype)
                _fgr, pha, *rec = model(src, *rec, downsample_ratio=downsample_ratio)
                pha = torch.where(pha < 0.03, torch.zeros_like(pha), pha)

                for index in range(len(frames)):
                    writer.stdin.write(rvm_frame_to_rgba(frames[index], pha, index))

                count += len(frames)
                now = time.perf_counter()
                if count == len(frames) or count % 30 == 0 or now - last_progress_at >= 5 or (total_frames and count >= total_frames):
                    elapsed = now - started
                    seconds_per_frame = elapsed / count
                    if total_frames:
                        percent = min(100.0, (count / total_frames) * 100)
                        remaining = max(0, total_frames - count) * seconds_per_frame
                        print(
                            f"Processed {count}/{total_frames} frames "
                            f"({percent:.1f}%, {seconds_per_frame:.2f}s/frame, "
                            f"elapsed {format_duration(elapsed)}, eta {format_duration(remaining)})",
                            flush=True,
                        )
                    else:
                        print(
                            f"Processed {count} frames "
                            f"({seconds_per_frame:.2f}s/frame, elapsed {format_duration(elapsed)})",
                            flush=True,
                        )
                    last_progress_at = now
    finally:
        capture.release()
        writer.stdin.close()
        writer.wait()

    return count


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Remove the background from a talking-head video and write a transparent MOV.")
    parser.add_argument("video", type=Path, help="Input video file")
    parser.add_argument("-o", "--output", type=Path, help="Output .mov path")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, choices=["rvm", "rembg"], help="Matting backend")
    parser.add_argument("--codec", default=DEFAULT_CODEC, choices=["prores", "qtrle"], help="Alpha MOV codec")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Segmentation model: u2net_human_seg, isnet-general-use, birefnet-portrait")
    parser.add_argument("--max-width", type=int, default=DEFAULT_MAX_WIDTH, help="Scale output to this width before segmentation; defaults to 0/source size")
    parser.add_argument("--rvm-downsample-ratio", type=float, default=0.125, help="RVM downsample ratio; 0.125 is the recommended 4K setting")
    parser.add_argument("--rvm-chunk", type=int, default=4, help="RVM frames per inference chunk")
    parser.add_argument("--shrink", type=int, default=DEFAULT_SHRINK, help="Shrink alpha edge by this many pixels")
    parser.add_argument("--blur", type=float, default=DEFAULT_BLUR, help="Blur alpha edge by this many pixels")
    parser.add_argument("--sample-seconds", type=float, help="Only process the first N seconds, useful for tuning")
    parser.add_argument("--preview", action="store_true", help="Also write a checkerboard MP4 preview")
    parser.add_argument("--alpha-matting", action="store_true", help="Use rembg alpha matting; slower and can print solver warnings")
    parser.add_argument("--no-audio", action="store_true", help="Do not copy audio from the source video")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    preload_onnxruntime_gpu_dlls()
    args = parse_args(argv or sys.argv[1:])
    input_path = args.video.resolve()

    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        return 1
    if input_path.suffix.lower() not in VIDEO_EXTENSIONS:
        print(f"Error: unsupported video extension: {input_path.suffix}", file=sys.stderr)
        return 1

    try:
        model = normalize_model(args.model)
        output_path = (args.output.resolve() if args.output else build_default_output_path(input_path, args.max_width))
        ffmpeg = find_ffmpeg()

        if args.backend == "rvm":
            print("Removing portrait background...")
            print(f"Input:  {input_path}")
            print(f"Output: {output_path}")
            print(f"Width:  {'source' if args.max_width <= 0 else args.max_width}")
            count = process_rvm_video(
                input_path=input_path,
                output_path=output_path,
                ffmpeg=ffmpeg,
                max_width=args.max_width,
                limit_seconds=args.sample_seconds,
                include_audio=not args.no_audio,
                downsample_ratio=args.rvm_downsample_ratio,
                chunk_size=args.rvm_chunk,
                codec=args.codec,
            )
            if count == 0:
                raise RuntimeError("No frames were processed.")
            if args.preview:
                print("Warning: --preview is not implemented for the RVM backend yet.")
            print("Done.")
            return 0

        with tempfile.TemporaryDirectory(prefix="remove-portrait-") as temp:
            frame_dir = Path(temp) / "alpha"
            print("Removing portrait background...")
            print(f"Input:  {input_path}")
            print(f"Output: {output_path}")
            print("Backend: rembg")
            print(f"Model:  {model}")
            print(f"Width:  {'source' if args.max_width <= 0 else args.max_width}")

            count, fps = process_frames(
                input_path=input_path,
                frame_dir=frame_dir,
                model=model,
                max_width=args.max_width,
                shrink=args.shrink,
                blur=args.blur,
                limit_seconds=args.sample_seconds,
                alpha_matting=args.alpha_matting,
            )
            if count == 0:
                raise RuntimeError("No frames were processed.")

            print("Writing transparent MOV...")
            subprocess.run(
                build_alpha_mov_command(
                    ffmpeg=ffmpeg,
                    frame_pattern=frame_dir / "%06d.png",
                    input_path=input_path,
                    output_path=output_path,
                    fps=fps,
                    include_audio=not args.no_audio,
                ),
                check=True,
            )

            if args.preview:
                preview_dir = Path(temp) / "checker"
                preview_path = build_preview_output_path(output_path)
                print("Writing checkerboard preview...")
                write_checker_preview_frames(frame_dir, preview_dir)
                subprocess.run(build_preview_command(ffmpeg, preview_dir / "%06d.png", preview_path, fps), check=True)
                print(f"Preview: {preview_path}")

        print("Done.")
        return 0
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
