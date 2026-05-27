class Logger:
    console_print: bool = False
    _log_storage: list[str] = []

    @staticmethod
    def log(message: str) -> None:
        decorator_message = "-" * 25 + "\n"
        if Logger.console_print:
            print(f"[LOG] {decorator_message}{message}{decorator_message}")
        Logger._log_storage.append(f"{decorator_message}{message}{decorator_message}")

    @staticmethod
    def error(message: str) -> None:
        decorator_message = "-" * 25 + "\n"
        if Logger.console_print:
            print(f"[ERROR] {decorator_message}{message}{decorator_message}")
        Logger._log_storage.append(f"{decorator_message}{message}{decorator_message}")

    @staticmethod
    def debug(message: str) -> None:
        decorator_message = "-" * 25 + "\n"
        if Logger.console_print:
            print(f"[DEBUG] {decorator_message}{message}{decorator_message}")
        Logger._log_storage.append(f"{decorator_message}{message}{decorator_message}")

    @staticmethod
    def get_logs() -> list[str]:
        return Logger._log_storage
    
    @staticmethod
    def clear_logs() -> None:
        Logger._log_storage = []

    @staticmethod
    def enable_console_logging() -> None:
        Logger.console_print = True