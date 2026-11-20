"""Split text files into sentence-aware chunks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Pattern


PROJECT_DIR = Path(__file__).resolve().parent
INPUT_DIR = PROJECT_DIR / "INPUT_CHUNK"
OUTPUT_DIR = PROJECT_DIR / "OUTPUT_CHUNK"
CONFIG_PATH = PROJECT_DIR / "chunk_config.json"


@dataclass(frozen=True)
class ChunkConfig:
    size: int
    buffer: int
    sentence_ending: Pattern[str]


def load_config(path: Path = CONFIG_PATH) -> ChunkConfig:
    with path.open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    if not isinstance(config, dict):
        raise ValueError("Chunk config must be a JSON object.")

    size = config.get("chunk_size_chars")
    buffer = config.get("chunk_buffer_chars")
    pattern = config.get("sentence_ending_pattern")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("'chunk_size_chars' must be a positive integer.")
    if isinstance(buffer, bool) or not isinstance(buffer, int) or buffer < 0:
        raise ValueError("'chunk_buffer_chars' must be a non-negative integer.")
    if not isinstance(pattern, str):
        raise ValueError("'sentence_ending_pattern' must be a string.")

    return ChunkConfig(size, buffer, re.compile(pattern))


def chunk_text(text: str, config: ChunkConfig) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        target = min(start + config.size, len(text))
        end = target
        if target < len(text):
            boundary = config.sentence_ending.search(text, start)
            while boundary and boundary.end() < target:
                boundary = config.sentence_ending.search(
                    text, max(boundary.end(), boundary.start() + 1)
                )
            if boundary and boundary.end() <= target + config.buffer:
                end = boundary.end()

        chunks.append(text[start:end])
        start = end
    return chunks


def chunk_file(source: Path, config: ChunkConfig) -> int:
    with source.open(encoding="utf-8", newline="") as input_file:
        chunks = chunk_text(input_file.read(), config)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, chunk in enumerate(chunks, start=1):
        destination = OUTPUT_DIR / f"{source.stem}_chunk_{index:04d}.txt"
        with destination.open("w", encoding="utf-8", newline="") as output_file:
            output_file.write(chunk)
    return len(chunks)


def cleanup_stale_chunks(expected_names: set[str]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    expected_names = {name.casefold() for name in expected_names}
    for path in OUTPUT_DIR.iterdir():
        if (
            path.is_file()
            and re.fullmatch(r".+_chunk_\d{4,}\.txt", path.name)
            and path.name.casefold() not in expected_names
        ):
            path.unlink()


def main() -> int:
    config = load_config()
    inputs = sorted(
        (
            path
            for path in INPUT_DIR.iterdir()
            if path.is_file() and path.suffix.lower() == ".txt"
        ),
        key=lambda path: path.name.lower(),
    )
    expected_names = set()
    for source in inputs:
        count = chunk_file(source, config)
        expected_names.update(
            f"{source.stem}_chunk_{index:04d}.txt"
            for index in range(1, count + 1)
        )
        print(f"{source.name}: wrote {count} chunk(s) to {OUTPUT_DIR}.")

    cleanup_stale_chunks(expected_names)
    if not inputs:
        print(f"No .txt input files found in {INPUT_DIR}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
