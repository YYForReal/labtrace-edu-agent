#!/usr/bin/env python3
"""Build the GOAI preliminary-round demo video from verified slide renders.

The script uses Edge neural TTS per scene, derives subtitle timings from the
actual audio durations, and produces a compatibility-first H.264/AAC MP4 with
a default Chinese subtitle track plus an external SRT file.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import edge_tts


ROOT = Path(__file__).resolve().parents[2]
GOAIHZ = ROOT / "goaihz"
SLIDES = GOAIHZ / "tmp" / "slides-rendered-lo"
WORK = GOAIHZ / "tmp" / "demo-video-v2"
SUBMISSION = GOAIHZ / "submission"
OUTPUT = SUBMISSION / "格物智评_LabTrace_初赛Demo.mp4"
SRT_OUTPUT = SUBMISSION / "格物智评_LabTrace_Demo.zh-CN.srt"
VOICE = "zh-CN-XiaoxiaoNeural"
RATE = "+15%"
PITCH = "-2Hz"
FPS = 25


@dataclass(frozen=True)
class Scene:
    slide: int
    narration: str


SCENES = [
    Scene(
        1,
        "格物智评 LabTrace，是面向高校教师的实验报告证据化批改 Agent："
        "让每一分回到证据，让批改进入教学闭环。",
    ),
    Scene(
        2,
        "五十七份游戏开发实验报告暴露三个痛点：证据散落、标准漂移、结果难沉淀。",
    ),
    Scene(
        3,
        "闭环包含理解任务、解析证据、逐项判断、确定校验、教师终审与教学诊断；"
        "GradeTrace 贯穿全程。",
    ),
    Scene(
        4,
        "同一骨架跨课程复用：生命科学核对对照和检测边界，"
        "游戏开发核对参数、日志与边界测试。",
    ),
    Scene(
        5,
        "评委选择合成案例，三分钟完成证据定位、评分、教师调整、发布、"
        "Word 与 JSON 下载和任务删除。",
    ),
    Scene(
        6,
        "过敏原 ELISA 案例证据充分，但缺少变异系数、回收率、异常值和检测限讨论，"
        "因此建议六十八分。",
    ),
    Scene(
        7,
        "Unity 案例已有参数、日志和三次运行，却缺少帧率、极端速度、"
        "边缘碰撞与连续重置测试，建议七十五分。",
    ),
    Scene(
        8,
        "低置信度不自动发布。教师查看逐项证据，把一项从八分调为十分；"
        "最终七十分，原建议仍保留。",
    ),
    Scene(
        9,
        "系统只聚合已复核数据：四份样本均分七十三点五，"
        "最弱维度达成率百分之五十三，并生成教学动作。",
    ),
    Scene(
        10,
        "生产容器限制一 GiB 内存、两个并发、二十五 MiB 上传；"
        "任务二十四小时删除，公开 Demo 零密钥。",
    ),
    Scene(
        11,
        "提交物包括网页、PPT 与 PDF、自然语音视频、双案例报告、部署测试和合规说明。"
        "独立变量，先把每一分讲清楚。",
    ),
]


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def media_duration(path: Path) -> float:
    payload = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )
    return float(json.loads(payload)["format"]["duration"])


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def caption_lines(text: str, width: int = 25) -> str:
    weights = [0.55 if ord(char) < 128 else 1.0 for char in text]
    total = sum(weights)
    if total <= width:
        return text
    midpoint = total / 2
    cumulative = 0.0
    candidates: list[tuple[float, int]] = []
    punctuation = "，。；：、！？ "
    for index, char_weight in enumerate(weights, start=1):
        cumulative += char_weight
        penalty = 0.0 if text[index - 1] in punctuation else 5.0
        candidates.append((abs(cumulative - midpoint) + penalty, index))
    split = min(
        candidates,
        key=lambda candidate: candidate[0],
    )[1]
    return f"{text[:split].rstrip()}\n{text[split:].lstrip()}"


async def synthesize(scene: Scene, output: Path) -> None:
    communicator = edge_tts.Communicate(
        scene.narration,
        VOICE,
        rate=RATE,
        pitch=PITCH,
    )
    await communicator.save(str(output))


async def synthesize_all() -> None:
    for index, scene in enumerate(SCENES, start=1):
        output = WORK / f"voice-{index:02d}.mp3"
        signature_file = WORK / f"voice-{index:02d}.sha256"
        signature = hashlib.sha256(
            f"{VOICE}\0{RATE}\0{PITCH}\0{scene.narration}".encode("utf-8")
        ).hexdigest()
        if (
            output.exists()
            and output.stat().st_size > 1024
            and signature_file.exists()
            and signature_file.read_text(encoding="utf-8").strip() == signature
        ):
            print(f"TTS {index:02d}/{len(SCENES)}: reuse {output.name}")
            continue
        await synthesize(scene, output)
        signature_file.write_text(f"{signature}\n", encoding="utf-8")
        print(f"TTS {index:02d}/{len(SCENES)}: {output.name}")


def build_scene(index: int, duration: float) -> Path:
    source = SLIDES / f"slide-{index}.png"
    target = WORK / f"scene-{index:02d}.mp4"
    audio = WORK / f"voice-{index:02d}.mp3"
    if not source.exists():
        raise FileNotFoundError(f"Missing verified slide render: {source}")
    if target.exists() and abs(media_duration(target) - duration) < 0.15:
        print(f"Video {index:02d}/{len(SCENES)}: reuse {target.name}")
        return target

    frames = max(1, round(duration * FPS))
    drift = 0.00018 if index % 2 else 0.00014
    x_expr = "iw/2-(iw/zoom/2)" if index % 3 else "iw-iw/zoom"
    y_expr = "ih/2-(ih/zoom/2)" if index % 4 else "ih-ih/zoom"
    video_filter = (
        "scale=1344:756:force_original_aspect_ratio=increase,"
        "crop=1344:756,"
        f"zoompan=z='min(zoom+{drift},1.035)':x='{x_expr}':y='{y_expr}':"
        f"d={frames}:s=1280x720:fps={FPS},"
        "format=yuv420p"
    )
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(source),
            "-i",
            str(audio),
            "-vf",
            video_filter,
            "-af",
            "apad=pad_dur=0.55,loudnorm=I=-18:LRA=7:TP=-1.5",
            "-t",
            f"{duration:.3f}",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(target),
        ]
    )
    print(f"Video {index:02d}/{len(SCENES)}: {target.name}")
    return target


def write_srt(durations: list[float]) -> None:
    cursor = 0.0
    blocks: list[str] = []
    for index, (scene, duration) in enumerate(zip(SCENES, durations), start=1):
        start = cursor + 0.12
        end = cursor + duration - 0.18
        blocks.append(
            f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n"
            f"{caption_lines(scene.narration)}\n"
        )
        cursor += duration
    SRT_OUTPUT.write_text("\n".join(blocks), encoding="utf-8")


def concat_scenes(scene_files: list[Path]) -> Path:
    manifest = WORK / "segments.txt"
    manifest.write_text(
        "\n".join(f"file '{path.as_posix()}'" for path in scene_files) + "\n",
        encoding="utf-8",
    )
    draft = WORK / "demo-draft.mp4"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(draft),
        ]
    )
    return draft


def mux_subtitles(draft: Path) -> None:
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(draft),
            "-i",
            str(SRT_OUTPUT),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-map",
            "1:s:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "mov_text",
            "-metadata:s:s:0",
            "language=zho",
            "-metadata:s:s:0",
            "title=简体中文字幕",
            "-disposition:s:0",
            "default",
            "-movflags",
            "+faststart",
            str(OUTPUT),
        ]
    )


def main() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg and ffprobe are required")
    WORK.mkdir(parents=True, exist_ok=True)
    SUBMISSION.mkdir(parents=True, exist_ok=True)

    asyncio.run(synthesize_all())
    durations = [
        media_duration(WORK / f"voice-{index:02d}.mp3") + 0.55
        for index in range(1, len(SCENES) + 1)
    ]
    write_srt(durations)
    scene_files = [
        build_scene(index, duration)
        for index, duration in enumerate(durations, start=1)
    ]
    draft = concat_scenes(scene_files)
    mux_subtitles(draft)
    print(
        f"Built {OUTPUT.name}: {media_duration(OUTPUT):.2f}s, "
        f"voice={VOICE}, scenes={len(SCENES)}"
    )


if __name__ == "__main__":
    main()
