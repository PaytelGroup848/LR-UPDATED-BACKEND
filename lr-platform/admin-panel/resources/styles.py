import tkinter as tk
from tkinter import ttk
from pathlib import Path


BG = '#f7f9fa'
SURFACE = '#ffffff'
TEXT = '#17211d'
MUTED = '#6b7671'
BORDER = '#dfe6e3'
HEADER_BG = '#ffffff'
PRIMARY = '#159a35'
SUCCESS = '#159a35'
DANGER = '#d64545'
WARNING = '#b7791f'
SOFT_GREEN = '#eaf7ed'
SIDEBAR = '#0b2028'
SIDEBAR_HOVER = '#14313a'
SIDEBAR_TEXT = '#d8e3df'


def resource_path(name):
    return Path(__file__).resolve().parent / name


def apply_style(root):
    root.configure(bg=BG)
    style = ttk.Style(root)
    try:
        style.theme_use('clam')
    except tk.TclError:
        pass
    style.configure('.', font=('Segoe UI', 10), foreground=TEXT)
    style.configure('TFrame', background=BG)
    style.configure('Surface.TFrame', background=SURFACE)
    style.configure('Card.TFrame', background=SURFACE, relief='flat')
    style.configure('TLabel', background=BG, foreground=TEXT)
    style.configure('Muted.TLabel', background=BG, foreground=MUTED)
    style.configure('Header.TLabel', background=HEADER_BG, foreground=TEXT, font=('Segoe UI', 17, 'bold'))
    style.configure('Treeview', rowheight=34, fieldbackground=SURFACE, background=SURFACE, foreground=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, relief='flat')
    style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'), background='#f7f9f8', foreground=TEXT, relief='flat', padding=(8, 9))
    style.map('Treeview', background=[('selected', SUCCESS)], foreground=[('selected', '#ffffff')])
    style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure('TNotebook.Tab', padding=(16, 9), font=('Segoe UI', 10, 'bold'), background='#edf5f1', foreground=MUTED, borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', SUCCESS), ('active', SOFT_GREEN)], foreground=[('selected', '#ffffff'), ('active', TEXT)])
    style.configure('TLabelframe', background=BG, foreground=TEXT, bordercolor=BORDER)
    style.configure('TLabelframe.Label', background=BG, foreground=TEXT, font=('Segoe UI', 10, 'bold'))
    style.configure('TEntry', fieldbackground=SURFACE, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.configure('TCombobox', fieldbackground=SURFACE, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    style.configure('TCheckbutton', background=BG, foreground=TEXT)
    style.configure('TRadiobutton', background=BG, foreground=TEXT)
    style.configure('Vertical.TScrollbar', background='#edf2f0', troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)

    # The notebook is a page stack; navigation is rendered in the sidebar.
    style.configure('Sidebar.TNotebook', background=BG, borderwidth=0, tabmargins=0)
    style.layout('Sidebar.TNotebook.Tab', [])


def button(parent, text, command, color=PRIMARY):
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=color,
        fg='white',
        activebackground='#117f2c' if color in (PRIMARY, SUCCESS) else color,
        activeforeground='white',
        relief=tk.FLAT,
        borderwidth=0,
        highlightthickness=0,
        padx=15,
        pady=8,
        cursor='hand2',
        font=('Segoe UI', 9, 'bold'),
    )


def plain_button(parent, text, command):
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg='#f1f4f3',
        fg=TEXT,
        activebackground='#e3ebe7',
        relief=tk.FLAT,
        borderwidth=0,
        highlightthickness=0,
        padx=12,
        pady=7,
        cursor='hand2',
        font=('Segoe UI', 9, 'bold'),
    )
