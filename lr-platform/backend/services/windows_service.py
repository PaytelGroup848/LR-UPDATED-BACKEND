from backend.services.secure_file_transfer_service import SecureFileTransferService


class WindowsFileService:

    @staticmethod
    def get_drives():
        return {
            "root": str(SecureFileTransferService.root()),
            "drives": ["."],
            "message": "File transfer is restricted to the secure transfer root",
        }, 200

    @staticmethod
    def browse(path):
        if not path:
            return {"message": "Path is required"}, 400

        try:
            return SecureFileTransferService.list_files(path), 200
        except (FileNotFoundError, NotADirectoryError, OSError, ValueError) as exc:
            return {"message": str(exc)}, 400

    @staticmethod
    def create_folder(path):
        if not path:
            return {"message": "Path is required"}, 400

        try:
            return SecureFileTransferService.create_folder(path), 200
        except (OSError, ValueError) as exc:
            return {"message": str(exc)}, 400

    @staticmethod
    def delete_path(path):
        if not path:
            return {"message": "Path is required"}, 400

        try:
            return SecureFileTransferService.delete(path), 200
        except (OSError, ValueError) as exc:
            return {"message": str(exc)}, 400

    @staticmethod
    def rename_file(old_path, new_path):
        if not old_path or not new_path:
            return {"message": "old_path and new_path are required"}, 400

        try:
            return SecureFileTransferService.rename(old_path, new_path), 200
        except (OSError, ValueError) as exc:
            return {"message": str(exc)}, 400

    @staticmethod
    def move_file(source, destination):
        if not source or not destination:
            return {"message": "source and destination are required"}, 400

        try:
            return SecureFileTransferService.move(source, destination), 200
        except (OSError, ValueError) as exc:
            return {"message": str(exc)}, 400

    @staticmethod
    def copy_file(source, destination):
        if not source or not destination:
            return {"message": "source and destination are required"}, 400

        try:
            return SecureFileTransferService.copy(source, destination), 200
        except (OSError, ValueError) as exc:
            return {"message": str(exc)}, 400

    @staticmethod
    def paste_path(source, destination, mode="copy", overwrite=False):
        if not source or not destination:
            return {"message": "source and destination are required"}, 400

        try:
            return SecureFileTransferService.paste(
                source,
                destination,
                mode=mode,
                overwrite=overwrite,
            ), 200
        except (OSError, ValueError) as exc:
            return {"message": str(exc)}, 400

    @staticmethod
    def upload_file(file, path):
        filename = file.filename if file else None

        if not file or not path or not filename:
            return {"message": "File and path are required"}, 400

        try:
            return SecureFileTransferService.upload(file, path), 200
        except (OSError, ValueError) as exc:
            return {"message": str(exc)}, 400

    @staticmethod
    def get_download_path(path):
        if not path:
            return {"message": "Path is required"}, 400

        try:
            target = SecureFileTransferService.download_path(path)
        except (FileNotFoundError, OSError, ValueError) as exc:
            return {"message": str(exc)}, 404

        if not target.is_file():
            return {"message": "File not found"}, 404

        return {
            "path": str(target),
            "download_name": target.name,
        }, 200
