from backend.services.secure_file_transfer_service import SecureFileTransferService


def _resolve_path(path):
    return SecureFileTransferService.resolve(path)


def list_files(path='.'):
    return SecureFileTransferService.list_files(path)


def read_file(path):
    return SecureFileTransferService.read_text(path)


def create_file(path, content=''):
    SecureFileTransferService.write_text(path, content)
    return 'File created'


def updated_file(path, content=''):
    SecureFileTransferService.write_text(path, content, overwrite=True)
    return 'File updated'


def deleted_file(path):
    result = SecureFileTransferService.delete(path)
    return result.get('message', 'Item deleted')
