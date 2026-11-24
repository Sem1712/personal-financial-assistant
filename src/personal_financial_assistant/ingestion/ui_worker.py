"""Isolated workbook operations for the local UI."""

import asyncio
import struct
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from .xlsx_reader import (
    FileSnapshot,
    ParsedFile,
    WorkbookError,
    check_snapshots,
    discover_workbooks,
    read_workbook,
)

CHUNK_SIZE = 65536


class WorkerRequest(BaseModel):
    operation: Literal["discover", "read", "verify"]
    directory: Path | None = None
    snapshot: FileSnapshot | None = None
    snapshots: list[FileSnapshot] | None = None


class WorkerResponse(BaseModel):
    snapshots: list[FileSnapshot] | None = None
    parsed: ParsedFile | None = None
    error: str | None = None


async def execute(request: WorkerRequest) -> WorkerResponse:
    """Run one file operation without accessing database resources."""
    try:
        if request.operation == "discover" and request.directory is not None:
            return WorkerResponse(snapshots=await discover_workbooks(request.directory))
        if request.operation == "read" and request.snapshot is not None:
            return WorkerResponse(parsed=await read_workbook(request.snapshot))
        if request.operation == "verify" and request.snapshots is not None:
            await check_snapshots(request.snapshots)
            return WorkerResponse()
        return WorkerResponse(error="Invalid worker request.")
    except WorkbookError as exc:
        return WorkerResponse(error=str(exc))


def main() -> None:
    """Exchange length-framed JSON messages over private standard pipes."""
    source = sys.stdin.buffer
    destination = sys.stdout.buffer
    while True:
        chunks: list[bytes] = []
        while True:
            header = source.read(4)
            if not header:
                return
            if len(header) != 4:
                return
            length = struct.unpack("!I", header)[0]
            if length == 0:
                break
            if length > CHUNK_SIZE:
                return
            chunk = source.read(length)
            if len(chunk) != length:
                return
            chunks.append(chunk)
        try:
            request = WorkerRequest.model_validate_json(b"".join(chunks))
        except ValidationError:
            response = WorkerResponse(error="Invalid worker request.")
        else:
            response = asyncio.run(execute(request))
        data = response.model_dump_json().encode()
        for offset in range(0, len(data), CHUNK_SIZE):
            part = data[offset : offset + CHUNK_SIZE]
            destination.write(struct.pack("!I", len(part)))
            destination.write(part)
        destination.write(struct.pack("!I", 0))
        destination.flush()


if __name__ == "__main__":
    main()
