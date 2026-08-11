import os
import shutil
from pathlib import Path
from typing import BinaryIO

from werkzeug.utils import secure_filename


class SecureFileTransferService:
    DEFAULT_MAX_READ_BYTES = 1_000_000
    DEFAULT_MAX_UPLOAD_BYTES = 100_000_000

    @staticmethod
    def root():
        try:
            from flask import current_app

            configured = current_app.config.get("FILE_TRANSFER_ROOT")
            instance_path = current_app.instance_path
        except RuntimeError:
            configured = None
            instance_path = os.path.join(os.getcwd(), "backend", "instance")

        root = configured or os.path.join(instance_path, "file_transfers")
        path = Path(root).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _max_upload_bytes():
        try:
            from flask import current_app

            return int(current_app.config.get("FILE_TRANSFER_MAX_UPLOAD_BYTES") or SecureFileTransferService.DEFAULT_MAX_UPLOAD_BYTES)
        except RuntimeError:
            return SecureFileTransferService.DEFAULT_MAX_UPLOAD_BYTES

    @staticmethod
    def _max_read_bytes():
        try:
            from flask import current_app

            return int(current_app.config.get("FILE_TRANSFER_MAX_READ_BYTES") or SecureFileTransferService.DEFAULT_MAX_READ_BYTES)
        except RuntimeError:
            return SecureFileTransferService.DEFAULT_MAX_READ_BYTES

    @staticmethod
    def resolve(path=".", *, must_exist=False):
        root = SecureFileTransferService.root()
        relative = str(path or ".").replace("\\", "/").lstrip("/")
        target = (root / relative).resolve()

        try:
            target.relative_to(root)
        except ValueError as error:
            raise ValueError("Path is outside the file transfer root") from error

        if must_exist and not target.exists():
            raise FileNotFoundError("Path not found")
        return target

    @staticmethod
    def relative(path):
        return str(path.resolve().relative_to(SecureFileTransferService.root())).replace("\\", "/")

    @staticmethod
    def list_files(path="."):
        target = SecureFileTransferService.resolve(path, must_exist=True)
        if not target.is_dir():
            raise NotADirectoryError("Directory not found")

        items = []
        for item in sorted(target.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower())):
            stat = item.stat()
            items.append({
                "name": item.name,
                "path": SecureFileTransferService.relative(item),
                "is_dir": item.is_dir(),
                "is_folder": item.is_dir(),
                "size": stat.st_size if item.is_file() else None,
                "modified_at": stat.st_mtime,
            })
        return {
            "root": str(SecureFileTransferService.root()),
            "path": SecureFileTransferService.relative(target) if target != SecureFileTransferService.root() else ".",
            "items": items,
        }

    @staticmethod
    def read_text(path):
        target = SecureFileTransferService.resolve(path, must_exist=True)
        if not target.is_file():
            raise FileNotFoundError("File not found")
        if target.stat().st_size > SecureFileTransferService._max_read_bytes():
            raise ValueError("File is too large to preview")
        return target.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def write_text(path, content="", *, overwrite=True):
        target = SecureFileTransferService.resolve(path)
        if target.exists() and not overwrite:
            raise FileExistsError("File already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content or ""), encoding="utf-8")
        return {"message": "File saved successfully", "path": SecureFileTransferService.relative(target)}

    @staticmethod
    def create_folder(path):
        target = SecureFileTransferService.resolve(path)
        target.mkdir(parents=True, exist_ok=True)
        return {"message": "Folder created successfully", "path": SecureFileTransferService.relative(target)}

    @staticmethod
    def upload(uploaded_file, path="."):
        if not uploaded_file or not uploaded_file.filename:
            raise ValueError("File is required")

        filename = secure_filename(uploaded_file.filename)
        if not filename:
            raise ValueError("Invalid filename")

        directory = SecureFileTransferService.resolve(path)
        directory.mkdir(parents=True, exist_ok=True)
        target = SecureFileTransferService.resolve(str(Path(SecureFileTransferService.relative(directory)) / filename))

        stream: BinaryIO = uploaded_file.stream
        max_bytes = SecureFileTransferService._max_upload_bytes()
        total = 0
        with target.open("wb") as handle:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise ValueError("Uploaded file is too large")
                handle.write(chunk)

        return {
            "message": "File uploaded successfully",
            "path": SecureFileTransferService.relative(target),
            "size": total,
        }

    @staticmethod
    def delete(path):
        target = SecureFileTransferService.resolve(path, must_exist=True)
        if target == SecureFileTransferService.root():
            raise ValueError("Cannot delete file transfer root")
        if target.is_dir():
            shutil.rmtree(target)
            return {"message": "Folder deleted successfully"}
        target.unlink()
        return {"message": "File deleted successfully"}

    @staticmethod
    def rename(old_path, new_path):
        source = SecureFileTransferService.resolve(old_path, must_exist=True)
        destination = SecureFileTransferService.resolve(new_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return {"message": "Item renamed successfully", "path": SecureFileTransferService.relative(destination)}

    @staticmethod
    def move(source, destination):
        source_path = SecureFileTransferService.resolve(source, must_exist=True)
        destination_path = SecureFileTransferService.resolve(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination_path))
        return {"message": "Item moved successfully", "path": SecureFileTransferService.relative(destination_path)}

    @staticmethod
    def copy(source, destination):
        source_path = SecureFileTransferService.resolve(source, must_exist=True)
        destination_path = SecureFileTransferService.resolve(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, destination_path)
        return {"message": "Item copied successfully", "path": SecureFileTransferService.relative(destination_path)}

    @staticmethod
    def _paste_destination(source_path, destination_dir, overwrite=False):
        destination_dir = SecureFileTransferService.resolve(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        if not destination_dir.is_dir():
            raise NotADirectoryError("Paste destination must be a folder")

        destination = destination_dir / source_path.name
        if overwrite or not destination.exists():
            return destination

        stem = source_path.stem
        suffix = source_path.suffix
        for index in range(1, 1000):
            candidate = destination_dir / f"{stem} - Copy {index}{suffix}"
            if not candidate.exists():
                return candidate

        raise FileExistsError("Could not create a unique paste filename")

    @staticmethod
    def paste(source, destination_dir=".", mode="copy", overwrite=False):
        source_path = SecureFileTransferService.resolve(source, must_exist=True)
        destination_path = SecureFileTransferService._paste_destination(
            source_path,
            destination_dir,
            overwrite=overwrite,
        )

        mode = str(mode or "copy").lower()
        if mode in {"cut", "move"}:
            shutil.move(str(source_path), str(destination_path))
            return {
                "message": "Item moved successfully",
                "operation": "move",
                "path": SecureFileTransferService.relative(destination_path),
            }

        if source_path.is_dir():
            shutil.copytree(source_path, destination_path, dirs_exist_ok=overwrite)
        else:
            shutil.copy2(source_path, destination_path)
        return {
            "message": "Item pasted successfully",
            "operation": "copy",
            "path": SecureFileTransferService.relative(destination_path),
        }

    @staticmethod
    def download_path(path):
        target = SecureFileTransferService.resolve(path, must_exist=True)
        if not target.is_file():
            raise FileNotFoundError("File not found")
        return target
