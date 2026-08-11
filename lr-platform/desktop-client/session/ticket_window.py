from tkinter import BOTH, END, X, Button, Entry, Frame, Label, Text, messagebox


class TicketWindowMixin:
    def show_ticket(self):
        self.clear()

        frame = Frame(self.root, padx=24, pady=24)
        frame.pack(fill=BOTH, expand=True)

        Label(frame, text='New Support Ticket', font=('Segoe UI', 18, 'bold')).pack(
            anchor='w',
            pady=(0, 12)
        )

        Label(frame, text='Title').pack(anchor='w')
        self.ticket_title_entry = Entry(frame)
        self.ticket_title_entry.pack(fill=X, pady=(4, 12))

        Label(frame, text='Description').pack(anchor='w')
        self.ticket_description = Text(frame, height=8)
        self.ticket_description.pack(fill=BOTH, expand=True)

        Button(frame, text='Create Ticket', command=self.create_ticket).pack(
            fill=X,
            pady=(12, 6)
        )
        Button(frame, text='Back', command=self.reload_apps).pack(fill=X)

        self.status = Label(frame, text='', fg='#666')
        self.status.pack(anchor='w', pady=(12, 0))

    def create_ticket(self):
        title = self.ticket_title_entry.get().strip()
        description = self.ticket_description.get('1.0', END).strip()

        if not title:
            messagebox.showerror('LR Remote Access', 'Ticket title is required.')
            return

        self.status.config(text='Creating ticket...')
        self.run_async(lambda: self._create_ticket(title, description))

    def _create_ticket(self, title, description):
        self.api.post_json(
            '/api/tickets',
            {'title': title, 'description': description, 'priority': 'normal'}
        )
        self.root.after(0, lambda: self.status.config(text='Ticket created.'))