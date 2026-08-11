import threading
from tkinter import messagebox


class AsyncRunnerMixin:
    def run_async(self, target):
        def wrapped():
            try:
                target()
            except Exception as error:
                self.root.after(
                    0,
                    lambda: messagebox.showerror('LR Remote Access', str(error))
                )
                self.root.after(0, lambda: self.status.config(text=''))

        threading.Thread(target=wrapped, daemon=True).start()