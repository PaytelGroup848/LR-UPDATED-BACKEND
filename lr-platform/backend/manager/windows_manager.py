from backend.services.secure_file_transfer_service import SecureFileTransferService


def get_drives():
    return ["."]


def browse_path(path):
    return SecureFileTransferService.list_files(path).get("items", [])


def create_folder(path):
    return SecureFileTransferService.create_folder(path)


def delete_path(path):
    return SecureFileTransferService.delete(path)


def rename_file(old_path, new_path):
    return SecureFileTransferService.rename(old_path, new_path)


def move_file(source, destination):
    return SecureFileTransferService.move(source, destination)


def copy_file(source, destination):
    return SecureFileTransferService.copy(source, destination)


def paste_path(source, destination, mode='copy', overwrite=False):
    return SecureFileTransferService.paste(source, destination, mode=mode, overwrite=overwrite)
