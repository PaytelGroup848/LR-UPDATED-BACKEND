from tkinter import BOTH, END, X, Button, Frame, Label, Text, messagebox


class ClipboardWindowMixin:
    def show_clipboard(self):
        self.clear()

        frame = Frame(self.root, padx=24, pady=24)
        frame.pack(fill=BOTH, expand=True)

        Label(frame, text='Clipboard Sync', font=('Segoe UI', 18, 'bold')).pack(
            anchor='w',
            pady=(0, 12)
        )

        self.clipboard_text = Text(frame, height=10)
        self.clipboard_text.pack(fill=BOTH, expand=True)

        Button(frame, text='Sync Clipboard', command=self.sync_clipboard).pack(
            fill=X,
            pady=(12, 6)
        )
        Button(frame, text='Back', command=self.reload_apps).pack(fill=X)

        self.status = Label(frame, text='', fg='#666')
        self.status.pack(anchor='w', pady=(12, 0))

    def sync_clipboard(self):
        content = self.clipboard_text.get('1.0', END).strip()

        if not content:
            messagebox.showerror('LR Remote Access', 'Clipboard text is required.')
            return

        self.status.config(text='Syncing clipboard...')
        self.run_async(lambda: self._sync_clipboard(content))

    def _sync_clipboard(self, content):
        self.api.post_json(
            '/api/clipboard',
            {'content': content, 'direction': 'client_to_remote'}
        )
        self.root.after(0, lambda: self.status.config(text='Clipboard synced.'))