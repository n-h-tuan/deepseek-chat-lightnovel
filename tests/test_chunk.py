import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import chunk


class ChunkTextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = chunk.ChunkConfig(
            size=10,
            buffer=4,
            sentence_ending=re.compile(r"[.!?]+[\"']*(?=\s|$)"),
        )

    def test_uses_sentence_boundary_inside_forward_buffer(self) -> None:
        text = "1234567890. next sentence"

        chunks = chunk.chunk_text(text, self.config)

        self.assertEqual(chunks, ["1234567890.", " next sent", "ence"])
        self.assertEqual("".join(chunks), text)
        self.assertLessEqual(len(chunks[0]), self.config.size + self.config.buffer)

    def test_hard_splits_when_no_boundary_is_in_buffer(self) -> None:
        text = "abcdefghijklmnop"

        chunks = chunk.chunk_text(text, self.config)

        self.assertEqual(chunks, ["abcdefghij", "klmnop"])
        self.assertEqual("".join(chunks), text)

    def test_ignores_zero_length_sentence_matches(self) -> None:
        config = chunk.ChunkConfig(10, 4, re.compile(r"^"))

        chunks = chunk.chunk_text("abcdefghijklmnop", config)

        self.assertEqual(chunks, ["abcdefghij", "klmnop"])

    def test_writes_chunks_for_an_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "book.txt"
            source.write_text("1234567890. next sentence", encoding="utf-8")
            output_dir = root / "output"

            with patch.object(chunk, "OUTPUT_DIR", output_dir):
                count = chunk.chunk_file(source, self.config)

            self.assertEqual(count, 3)
            self.assertEqual(
                (output_dir / "book_chunk_0001.txt").read_text(encoding="utf-8"),
                "1234567890.",
            )
            self.assertEqual(
                "".join(
                    path.read_text(encoding="utf-8")
                    for path in sorted(output_dir.iterdir())
                ),
                "1234567890. next sentence",
            )

    def test_cleanup_removes_only_stale_chunk_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            (output_dir / "book_chunk_0001.txt").write_text("current")
            (output_dir / "book_chunk_0002.txt").write_text("stale")
            (output_dir / "notes.txt").write_text("keep")

            with patch.object(chunk, "OUTPUT_DIR", output_dir):
                chunk.cleanup_stale_chunks({"book_chunk_0001.txt"})

            self.assertEqual(
                sorted(path.name for path in output_dir.iterdir()),
                ["book_chunk_0001.txt", "notes.txt"],
            )


if __name__ == "__main__":
    unittest.main()
