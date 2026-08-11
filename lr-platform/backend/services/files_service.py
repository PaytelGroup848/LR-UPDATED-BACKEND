from backend.services.secure_file_transfer_service import SecureFileTransferService


class FileService:

    @staticmethod
    def _safe_path(base_path, root="."):
        return str(SecureFileTransferService.resolve(base_path or root))

    @staticmethod
    def list_files(base_path, root="."):
        return SecureFileTransferService.list_files(base_path)

    @staticmethod
    def read_file_content(path):

        if not path:
            return {
                "message": "Path is required"
            }, 400

        try:
            return {"content": SecureFileTransferService.read_text(path)}, 200
        except (OSError, ValueError) as error:
            return {
                "message": str(error)
            }, 400

    @staticmethod
    def create_file_content(path, content=""):

        if not path:
            return {
                "message": "Path is required"
            }, 400

        try:
            return SecureFileTransferService.write_text(path, content), 200
        except (OSError, ValueError) as error:
            return {
                "message": str(error)
            }, 400

    @staticmethod
    def upload_file_content(uploaded_file, path):

        if not uploaded_file or not path:
            return {
                "message": "File and path are required"
            }, 400

        try:
            return SecureFileTransferService.upload(uploaded_file, path), 200
        except (OSError, ValueError) as error:
            return {
                "message": str(error)
            }, 400

    @staticmethod
    def delete_file_content(path, user_id=None):

        if not path:
            return {
                "message": "Path is required"
            }, 400

        try:
            return SecureFileTransferService.delete(path), 200
        except (OSError, ValueError) as error:
            return {
                "message": str(error)
            }, 400

    @staticmethod
    def paste_file_content(source, destination, mode="copy", overwrite=False):
        if not source or not destination:
            return {
                "message": "source and destination are required"
            }, 400

        try:
            return SecureFileTransferService.paste(
                source,
                destination,
                mode=mode,
                overwrite=overwrite,
            ), 200
        except (OSError, ValueError) as error:
            return {
                "message": str(error)
            }, 400
