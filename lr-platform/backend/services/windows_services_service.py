import platform

from backend.manager.windows_services_manager import (
    get_services,
    start_service,
    stop_service
)


class WindowsServiceManagerService:

    @staticmethod
    def list_services():
        if platform.system() != "Windows":
            return (
                "<pre>Service management is only supported on Windows hosts.</pre>",
                501
            )

        return f"<pre>{get_services()}</pre>", 200

    @staticmethod
    def start_windows_service(service_name):
        if not service_name:
            return "<pre>service_name is required</pre>", 400

        if platform.system() != "Windows":
            return (
                "<pre>Service management is only supported on Windows hosts.</pre>",
                501
            )

        return f"<pre>{start_service(service_name)}</pre>", 200

    @staticmethod
    def stop_windows_service(service_name):
        if not service_name:
            return "<pre>service_name is required</pre>", 400

        if platform.system() != "Windows":
            return (
                "<pre>Service management is only supported on Windows hosts.</pre>",
                501
            )

        return f"<pre>{stop_service(service_name)}</pre>", 200
