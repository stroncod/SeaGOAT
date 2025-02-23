import hashlib
from typing import Dict
from typing import List
from typing import Literal

from seagoat.utils.file_reader import read_file_with_correct_encoding


class File:
    def __init__(
        self, path: str, absolute_path: str, score: float, commit_messages: list[str]
    ):
        self.path = path
        self.absolute_path = absolute_path
        self.commit_hashes = set()
        self.score = score
        self.commit_messages = commit_messages

    def __repr__(self):
        return f"<File {self.path} {self.score}>"

    def add_commit(self, commit_hash: str):
        self.commit_hashes.add(commit_hash)

    def get_metadata(self):
        commit_messages = "\n-".join(sorted(self.commit_messages))
        return f"""###
    Filename: {self.path}
    Commits:
{commit_messages}"""

    def _get_file_lines(self) -> Dict[int, str]:
        lines = {
            (i + 1): line
            for i, line in enumerate(
                read_file_with_correct_encoding(self.absolute_path).splitlines()
            )
        }

        return lines

    def _format_chunk_summary(self, relevant_lines: List[str]):
        truncated_lines = [line[:100] for line in relevant_lines]
        chunk = "\n".join(truncated_lines)
        chunk = chunk + self.get_metadata()

        return chunk

    def _get_context_lines(
        self, lines: Dict[int, str], line_number: int, direction: Literal[-1, 1]
    ) -> List[str]:
        context_lines = []
        for i in range(1, 6):
            current_line_number = line_number + (direction * i)
            current_line = lines.get(current_line_number)

            if current_line is None:
                break

            if direction == -1:
                context_lines = [current_line] + context_lines
            else:
                context_lines.append(current_line)

            if self._line_has_relevant_data(current_line):
                break

        return context_lines

    def _get_chunk_for_line(self, line_number: int, lines: Dict[int, str]):
        relevant_lines = (
            self._get_context_lines(lines, line_number, -1)
            + [lines[line_number]]
            + self._get_context_lines(lines, line_number, 1)
        )
        return FileChunk(self, line_number, self._format_chunk_summary(relevant_lines))

    def _line_has_relevant_data(self, line: str):
        return sum(c.isalnum() for c in line) > 3

    def get_chunks(self):
        lines = self._get_file_lines()
        return [
            self._get_chunk_for_line(line_number, lines)
            for line_number in lines.keys()
            if self._line_has_relevant_data(lines[line_number])
        ]


# pylint: disable=too-few-public-methods
class FileChunk:
    def __init__(self, parent: File, codeline: int, chunk: str):
        self.path = parent.path
        self.codeline = codeline
        self.chunk = chunk
        self.chunk_id = self._get_id()

    def _get_id(self):
        text = f"""
        Path: {self.path}
        Code line: {self.codeline}
        Chunk: {self.chunk}
        """
        return hashlib.sha256(text.encode()).hexdigest()

    def __repr__(self) -> str:
        return f"<FileChunk {self.path} {self.codeline}>"
