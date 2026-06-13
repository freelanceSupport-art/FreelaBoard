from __future__ import annotations

import sys
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .store import (
    ALL_FILTER,
    DUE_FILTERS,
    FINAL_STATUSES,
    INVOICE_STATES,
    PAYMENT_STATES,
    STATUSES,
    ProjectStore,
    days_until,
    deadline_notice_signature,
    describe_due,
)
from .windows_notify import WindowsNotifier


PALETTE = {
    "void": "#05070d",
    "space": "#09111d",
    "deck": "#0d1726",
    "deck_2": "#101f31",
    "field": "#071321",
    "line": "#1b3650",
    "line_hot": "#39e8ff",
    "text": "#ecf7ff",
    "muted": "#8397aa",
    "cyan": "#39e8ff",
    "mint": "#4ff5b1",
    "pink": "#ff4ed2",
    "amber": "#ffd166",
    "red": "#ff5277",
    "blue": "#7aa7ff",
}

CHECK_INTERVAL_MS = 30 * 60 * 1000


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative_path


def format_yen(value: object) -> str:
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,}円"


class NeonSwitch(tk.Canvas):
    def __init__(
        self,
        parent: tk.Misc,
        variable: tk.BooleanVar,
        command: object | None = None,
    ) -> None:
        super().__init__(
            parent,
            width=58,
            height=28,
            bg=PALETTE["deck"],
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.variable = variable
        self.command = command
        self.bind("<Button-1>", self._toggle)
        self.variable.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _toggle(self, _event: tk.Event) -> None:
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def _draw(self) -> None:
        self.delete("all")
        active = self.variable.get()
        fill = "#113c46" if active else "#162033"
        outline = PALETTE["cyan"] if active else PALETTE["line"]
        knob = PALETTE["mint"] if active else "#5c6a7a"
        text = "ON" if active else "OFF"
        self.create_rectangle(2, 5, 56, 23, outline=outline, fill=fill, width=2)
        x0 = 35 if active else 7
        self.create_rectangle(x0, 8, x0 + 16, 20, outline=knob, fill=knob)
        self.create_text(
            29,
            14,
            text=text,
            fill=PALETTE["text"] if active else PALETTE["muted"],
            font=("Segoe UI", 7, "bold"),
        )


class FreelaBoardApp(tk.Tk):
    def __init__(self, store: ProjectStore | None = None) -> None:
        super().__init__()
        self.title("FreelaBoard")
        self.geometry("1360x820")
        self.minsize(1220, 720)
        self.configure(bg=PALETTE["void"])

        self.store = store or ProjectStore()
        settings = self.store.settings()
        self.selected_id: int | None = None
        self._is_refreshing = False
        self._hidden_resident = False
        self._force_exit = False
        self._deadline_after: str | None = None

        self.search_var = tk.StringVar()
        self.status_filter_var = tk.StringVar(value=ALL_FILTER)
        self.due_filter_var = tk.StringVar(value=ALL_FILTER)
        self.notifications_var = tk.BooleanVar(value=settings.deadline_notifications)
        self.resident_var = tk.BooleanVar(value=settings.resident_on_close)
        self.notification_days_var = tk.StringVar(value=str(settings.notification_days))
        self.status_text = tk.StringVar(value=f"DB {self.store.db_path}")
        self.metric_vars = {
            "total": tk.StringVar(value="0"),
            "active": tk.StringVar(value="0"),
            "deadline": tk.StringVar(value="0"),
            "unpaid": tk.StringVar(value="0円"),
            "paid": tk.StringVar(value="0円"),
        }
        self.form_vars = {
            "title": tk.StringVar(),
            "client": tk.StringVar(),
            "status": tk.StringVar(value=STATUSES[0]),
            "due_date": tk.StringVar(),
            "amount": tk.StringVar(value="0"),
            "invoice_state": tk.StringVar(value=INVOICE_STATES[0]),
            "payment_state": tk.StringVar(value=PAYMENT_STATES[0]),
        }

        self._configure_style()
        self._set_window_icon()
        self._build_ui()
        self._wire_events()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.update_idletasks()
        self.notifier = WindowsNotifier(
            self.winfo_id(),
            resource_path("assets/generated/freelaboard.ico"),
            self._restore_from_resident,
            self._exit_from_tray,
        )
        self._sync_tray_icon()
        self._new_project()
        self._refresh_all()
        self.after(1400, lambda: self._check_deadline_notifications(force=False))

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Neo.Treeview",
            background=PALETTE["field"],
            foreground=PALETTE["text"],
            fieldbackground=PALETTE["field"],
            borderwidth=0,
            rowheight=38,
            font=("Yu Gothic UI", 10),
        )
        style.map(
            "Neo.Treeview",
            background=[("selected", "#144d5d")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Neo.Treeview.Heading",
            background=PALETTE["deck_2"],
            foreground=PALETTE["cyan"],
            relief="flat",
            font=("Yu Gothic UI", 9, "bold"),
        )
        style.map("Neo.Treeview.Heading", background=[("active", "#14324c")])
        style.configure(
            "Neo.Vertical.TScrollbar",
            troughcolor=PALETTE["space"],
            background=PALETTE["line"],
            arrowcolor=PALETTE["cyan"],
            bordercolor=PALETTE["space"],
            lightcolor=PALETTE["line"],
            darkcolor=PALETTE["line"],
        )
        style.configure(
            "Neo.TCombobox",
            fieldbackground=PALETTE["field"],
            background=PALETTE["deck_2"],
            foreground=PALETTE["text"],
            arrowcolor=PALETTE["cyan"],
            bordercolor=PALETTE["line"],
            lightcolor=PALETTE["line"],
            darkcolor=PALETTE["line"],
        )
        style.map(
            "Neo.TCombobox",
            fieldbackground=[("readonly", PALETTE["field"])],
            foreground=[("readonly", PALETTE["text"])],
            selectbackground=[("readonly", PALETTE["field"])],
            selectforeground=[("readonly", PALETTE["text"])],
        )

    def _set_window_icon(self) -> None:
        if sys.platform.startswith("win"):
            try:
                import ctypes

                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "FreelaBoard.Desktop"
                )
            except Exception:
                pass

        ico = resource_path("assets/generated/freelaboard.ico")
        if ico.exists():
            try:
                self.iconbitmap(default=str(ico))
            except tk.TclError:
                pass

        png = resource_path("assets/generated/freelaboard.png")
        if png.exists():
            try:
                self._window_icon_photo = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._window_icon_photo)
            except tk.TclError:
                pass

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        rail = tk.Frame(self, bg="#03060b", width=184)
        rail.grid(row=0, column=0, rowspan=3, sticky="ns")
        rail.grid_propagate(False)
        self._build_rail(rail)

        top = tk.Frame(self, bg=PALETTE["void"], padx=18, pady=16)
        top.grid(row=0, column=1, sticky="ew")
        top.columnconfigure(1, weight=1)
        self._build_header(top)

        body = tk.Frame(self, bg=PALETTE["void"], padx=18, pady=0)
        body.grid(row=1, column=1, sticky="nsew", pady=(0, 14))
        body.columnconfigure(0, weight=7, minsize=680)
        body.columnconfigure(1, weight=3, minsize=360)
        body.rowconfigure(0, weight=1)

        self._build_stream(body)
        self._build_control_deck(body)

        status = tk.Frame(self, bg="#03060b", padx=14, pady=8)
        status.grid(row=2, column=1, sticky="ew")
        tk.Label(
            status,
            textvariable=self.status_text,
            bg="#03060b",
            fg=PALETTE["muted"],
            anchor="w",
            font=("Consolas", 9),
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            status,
            text="LOCAL / SQLITE / SINGLE EXE",
            bg="#03060b",
            fg=PALETTE["cyan"],
            font=("Consolas", 9, "bold"),
        ).pack(side="right")

    def _build_rail(self, parent: tk.Frame) -> None:
        parent.pack_propagate(False)
        tk.Label(
            parent,
            text="FreelaBoard",
            bg="#03060b",
            fg=PALETTE["cyan"],
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=14, pady=(18, 2))
        tk.Label(
            parent,
            text="操作メニュー",
            bg="#03060b",
            fg=PALETTE["muted"],
            font=("Yu Gothic UI", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(0, 22))

        self._rail_section(parent, "案件操作")
        self._rail_button(
            parent,
            "新規案件",
            "入力欄をクリア",
            self._new_project,
            PALETTE["cyan"],
        ).pack(fill="x", padx=10, pady=(0, 8))
        self._rail_button(
            parent,
            "保存",
            "現在の内容を反映",
            self._save_project,
            PALETTE["mint"],
        ).pack(fill="x", padx=10, pady=(0, 8))
        self._rail_button(
            parent,
            "CSV出力",
            "表示中の一覧を保存",
            self._export_csv,
            PALETTE["blue"],
        ).pack(fill="x", padx=10, pady=(0, 16))

        self._rail_section(parent, "通知")
        self._rail_button(
            parent,
            "期限通知を確認",
            "今すぐチェック",
            lambda: self._check_deadline_notifications(force=True),
            PALETTE["amber"],
        ).pack(fill="x", padx=10, pady=(0, 8))

        tk.Frame(parent, bg="#03060b").pack(fill="both", expand=True)
        tk.Frame(parent, bg=PALETTE["line"], height=1).pack(fill="x", padx=14, pady=(0, 12))
        self._rail_button(
            parent,
            "終了",
            "",
            self._exit_app,
            PALETTE["red"],
            danger=True,
        ).pack(fill="x", padx=10, pady=(0, 18))

    def _build_header(self, parent: tk.Frame) -> None:
        brand = tk.Canvas(
            parent,
            width=350,
            height=78,
            bg=PALETTE["void"],
            bd=0,
            highlightthickness=0,
        )
        brand.grid(row=0, column=0, sticky="w")
        brand.create_line(4, 60, 338, 60, fill=PALETTE["line_hot"], width=2)
        brand.create_line(220, 60, 252, 42, fill=PALETTE["pink"], width=2)
        brand.create_text(
            5,
            22,
            text="FreelaBoard",
            fill=PALETTE["text"],
            anchor="w",
            font=("Segoe UI", 25, "bold"),
        )
        brand.create_text(
            7,
            48,
            text="FUTURE CONTRACT OPERATIONS",
            fill=PALETTE["cyan"],
            anchor="w",
            font=("Consolas", 9, "bold"),
        )

        metrics = tk.Frame(parent, bg=PALETTE["void"])
        metrics.grid(row=0, column=1, sticky="e")
        self._metric(metrics, "TOTAL", self.metric_vars["total"], PALETTE["cyan"]).pack(side="left", padx=5)
        self._metric(metrics, "ACTIVE", self.metric_vars["active"], PALETTE["mint"]).pack(side="left", padx=5)
        self._metric(metrics, "DUE", self.metric_vars["deadline"], PALETTE["amber"]).pack(side="left", padx=5)
        self._metric(metrics, "UNPAID", self.metric_vars["unpaid"], PALETTE["pink"]).pack(side="left", padx=5)
        self._metric(metrics, "PAID", self.metric_vars["paid"], PALETTE["blue"]).pack(side="left", padx=5)

    def _build_stream(self, parent: tk.Frame) -> None:
        stream = self._holo_panel(parent, padx=14, pady=14)
        stream.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        stream.columnconfigure(0, weight=1)
        stream.rowconfigure(2, weight=1)

        title_row = tk.Frame(stream, bg=PALETTE["deck"])
        title_row.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        title_row.columnconfigure(1, weight=1)
        tk.Label(
            title_row,
            text="CONTRACT STREAM",
            bg=PALETTE["deck"],
            fg=PALETTE["cyan"],
            font=("Consolas", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            title_row,
            text="納期優先ソート",
            bg=PALETTE["deck"],
            fg=PALETTE["muted"],
            font=("Yu Gothic UI", 9),
        ).grid(row=0, column=1, sticky="e")

        filters = tk.Frame(stream, bg=PALETTE["deck"])
        filters.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        filters.columnconfigure(0, weight=1)
        self._entry(filters, self.search_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._combo(filters, self.status_filter_var, (ALL_FILTER, *STATUSES), 12).grid(row=0, column=1, padx=(0, 8))
        self._combo(filters, self.due_filter_var, DUE_FILTERS, 12).grid(row=0, column=2, padx=(0, 8))
        self._neo_button(filters, "CSV", self._export_csv, PALETTE["mint"]).grid(row=0, column=3)

        table_shell = tk.Frame(stream, bg=PALETTE["line"], padx=1, pady=1)
        table_shell.grid(row=2, column=0, sticky="nsew")
        table_shell.columnconfigure(0, weight=1)
        table_shell.rowconfigure(0, weight=1)
        self.table = ttk.Treeview(
            table_shell,
            columns=("title", "client", "status", "due", "invoice", "payment", "amount"),
            show="headings",
            selectmode="browse",
            style="Neo.Treeview",
        )
        headings = {
            "title": ("案件", 230, "w"),
            "client": ("CLIENT", 150, "w"),
            "status": ("STATUS", 94, "center"),
            "due": ("DEADLINE", 166, "center"),
            "invoice": ("請求", 86, "center"),
            "payment": ("入金", 86, "center"),
            "amount": ("AMOUNT", 112, "e"),
        }
        for key, (label, width, anchor) in headings.items():
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=70, anchor=anchor, stretch=True)
        self.table.tag_configure("overdue", background="#32111d", foreground="#ffe5ee")
        self.table.tag_configure("soon", background="#332812", foreground="#fff2ca")
        self.table.tag_configure("paid", background="#0d2c27", foreground="#dcfff3")
        self.table.tag_configure("final", background="#111d2c", foreground="#b9c8dc")
        self.table.tag_configure("normal", background=PALETTE["field"], foreground=PALETTE["text"])
        yscroll = ttk.Scrollbar(
            table_shell, orient="vertical", command=self.table.yview, style="Neo.Vertical.TScrollbar"
        )
        self.table.configure(yscrollcommand=yscroll.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

    def _build_control_deck(self, parent: tk.Frame) -> None:
        shell = self._holo_panel(parent, padx=8, pady=8)
        shell.grid(row=0, column=1, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            shell,
            bg=PALETTE["deck"],
            bd=0,
            highlightthickness=0,
            yscrollincrement=24,
        )
        scrollbar = ttk.Scrollbar(
            shell,
            orient="vertical",
            command=canvas.yview,
            style="Neo.Vertical.TScrollbar",
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))

        deck = tk.Frame(canvas, bg=PALETTE["deck"], padx=6, pady=6)
        deck_window = canvas.create_window((0, 0), window=deck, anchor="nw")
        deck.columnconfigure(1, weight=1)
        deck.rowconfigure(15, weight=1)

        def sync_scroll_region(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_deck_width(event: tk.Event) -> None:
            canvas.itemconfigure(deck_window, width=event.width)

        def on_mousewheel(event: tk.Event) -> str:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        deck.bind("<Configure>", sync_scroll_region)
        canvas.bind("<Configure>", sync_deck_width)
        shell.bind("<Enter>", lambda _event: self.bind_all("<MouseWheel>", on_mousewheel))
        shell.bind("<Leave>", lambda _event: self.unbind_all("<MouseWheel>"))

        tk.Label(
            deck,
            text="OPS DOCK",
            bg=PALETTE["deck"],
            fg=PALETTE["pink"],
            font=("Consolas", 14, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        self._field(deck, 1, "案件名", self._entry(deck, self.form_vars["title"]))
        self._field(deck, 2, "CLIENT", self._entry(deck, self.form_vars["client"]))
        self._field(deck, 3, "STATUS", self._combo(deck, self.form_vars["status"], STATUSES))
        self._field(deck, 4, "納期", self._entry(deck, self.form_vars["due_date"]))

        jump = tk.Frame(deck, bg=PALETTE["deck"])
        jump.grid(row=5, column=1, sticky="w", pady=(0, 10))
        self._mini_button(jump, "今日", lambda: self._set_due_days(0)).pack(side="left", padx=(0, 5))
        self._mini_button(jump, "+7", lambda: self._set_due_days(7)).pack(side="left", padx=(0, 5))
        self._mini_button(jump, "+30", lambda: self._set_due_days(30)).pack(side="left")

        self._field(deck, 6, "金額", self._entry(deck, self.form_vars["amount"]))
        self._field(deck, 7, "請求", self._combo(deck, self.form_vars["invoice_state"], INVOICE_STATES))
        self._field(deck, 8, "入金", self._combo(deck, self.form_vars["payment_state"], PAYMENT_STATES))

        tk.Label(
            deck,
            text="MEMO",
            bg=PALETTE["deck"],
            fg=PALETTE["muted"],
            font=("Consolas", 9, "bold"),
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(6, 5))
        self.memo_text = tk.Text(
            deck,
            height=7,
            bg=PALETTE["field"],
            fg=PALETTE["text"],
            insertbackground=PALETTE["cyan"],
            relief="flat",
            wrap="word",
            font=("Yu Gothic UI", 10),
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
            highlightcolor=PALETTE["cyan"],
        )
        self.memo_text.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(0, 12))

        actions = tk.Frame(deck, bg=PALETTE["deck"])
        actions.grid(row=11, column=0, columnspan=2, sticky="ew")
        actions.columnconfigure((0, 1), weight=1)
        self._neo_button(actions, "保存", self._save_project, PALETTE["cyan"]).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._neo_button(actions, "削除", self._delete_project, PALETTE["red"]).grid(row=0, column=1, sticky="ew")

        self._separator(deck, 12)

        tk.Label(
            deck,
            text="SYSTEM FLAGS",
            bg=PALETTE["deck"],
            fg=PALETTE["cyan"],
            font=("Consolas", 11, "bold"),
        ).grid(row=13, column=0, columnspan=2, sticky="w", pady=(2, 10))

        self._switch_row(deck, 14, "期限通知", self.notifications_var, self._on_notifications_toggle)
        self._switch_row(deck, 15, "閉じたら常駐", self.resident_var, self._on_resident_toggle)
        self._field(deck, 16, "通知範囲(日)", self._spinbox(deck, self.notification_days_var))
        self._neo_button(deck, "通知テスト", lambda: self._check_deadline_notifications(force=True), PALETTE["amber"]).grid(
            row=17, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

    def _wire_events(self) -> None:
        self.table.bind("<<TreeviewSelect>>", self._on_select)
        self.search_var.trace_add("write", lambda *_: self._refresh_table())
        self.status_filter_var.trace_add("write", lambda *_: self._refresh_table())
        self.due_filter_var.trace_add("write", lambda *_: self._refresh_table())
        self.notification_days_var.trace_add("write", lambda *_: self._save_notification_days())

    def _holo_panel(self, parent: tk.Misc, padx: int, pady: int) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=PALETTE["deck"],
            padx=padx,
            pady=pady,
            highlightthickness=1,
            highlightbackground=PALETTE["cyan"],
        )

    def _separator(self, parent: tk.Misc, row: int) -> None:
        tk.Frame(parent, bg=PALETTE["line"], height=1).grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=14
        )

    def _metric(self, parent: tk.Misc, label: str, variable: tk.StringVar, color: str) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=PALETTE["deck"],
            padx=13,
            pady=8,
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
        )
        tk.Label(
            frame,
            text=label,
            bg=PALETTE["deck"],
            fg=PALETTE["muted"],
            font=("Consolas", 8, "bold"),
        ).pack(anchor="w")
        tk.Label(
            frame,
            textvariable=variable,
            bg=PALETTE["deck"],
            fg=color,
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        return frame

    def _rail_section(self, parent: tk.Misc, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg="#03060b",
            fg=PALETTE["muted"],
            font=("Yu Gothic UI", 9, "bold"),
        ).pack(anchor="w", padx=14, pady=(0, 8))

    def _rail_button(
        self,
        parent: tk.Misc,
        title: str,
        subtitle: str,
        command: object,
        accent: str,
        danger: bool = False,
    ) -> tk.Button:
        bg = "#141b2a" if not danger else "#351320"
        active = "#173448" if not danger else "#5a1b2f"
        text = f"{title}\n{subtitle}" if subtitle else title
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=accent,
            activebackground=active,
            activeforeground=PALETTE["text"],
            relief="flat",
            bd=0,
            padx=10,
            pady=9,
            cursor="hand2",
            anchor="w",
            justify="left",
            font=("Yu Gothic UI", 10, "bold"),
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
        )

    def _entry(self, parent: tk.Misc, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=variable,
            bg=PALETTE["field"],
            fg=PALETTE["text"],
            insertbackground=PALETTE["cyan"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
            highlightcolor=PALETTE["cyan"],
            font=("Yu Gothic UI", 10),
        )

    def _combo(
        self, parent: tk.Misc, variable: tk.StringVar, values: tuple[str, ...], width: int = 18
    ) -> ttk.Combobox:
        return ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
            width=width,
            style="Neo.TCombobox",
            font=("Yu Gothic UI", 10),
        )

    def _spinbox(self, parent: tk.Misc, variable: tk.StringVar) -> tk.Spinbox:
        return tk.Spinbox(
            parent,
            from_=1,
            to=30,
            textvariable=variable,
            bg=PALETTE["field"],
            fg=PALETTE["text"],
            buttonbackground=PALETTE["deck_2"],
            insertbackground=PALETTE["cyan"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
            highlightcolor=PALETTE["cyan"],
            font=("Yu Gothic UI", 10),
            width=8,
            command=self._save_notification_days,
        )

    def _neo_button(self, parent: tk.Misc, text: str, command: object, color: str) -> tk.Button:
        dark_fg = color in {PALETTE["cyan"], PALETTE["mint"], PALETTE["amber"]}
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg=PALETTE["void"] if dark_fg else PALETTE["text"],
            activebackground=PALETTE["pink"],
            activeforeground=PALETTE["text"],
            relief="flat",
            bd=0,
            padx=13,
            pady=8,
            cursor="hand2",
            font=("Yu Gothic UI", 10, "bold"),
        )

    def _mini_button(self, parent: tk.Misc, text: str, command: object) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=PALETTE["deck_2"],
            fg=PALETTE["cyan"],
            activebackground=PALETTE["cyan"],
            activeforeground=PALETTE["void"],
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            font=("Yu Gothic UI", 9, "bold"),
        )

    def _field(self, parent: tk.Misc, row: int, label: str, widget: tk.Widget) -> None:
        tk.Label(
            parent,
            text=label,
            bg=PALETTE["deck"],
            fg=PALETTE["muted"],
            font=("Yu Gothic UI", 9, "bold"),
        ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(0, 10))
        widget.grid(row=row, column=1, sticky="ew", pady=(0, 10))

    def _switch_row(
        self,
        parent: tk.Misc,
        row: int,
        label: str,
        variable: tk.BooleanVar,
        command: object,
    ) -> None:
        tk.Label(
            parent,
            text=label,
            bg=PALETTE["deck"],
            fg=PALETTE["muted"],
            font=("Yu Gothic UI", 9, "bold"),
        ).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(0, 10))
        NeonSwitch(parent, variable, command).grid(row=row, column=1, sticky="w", pady=(0, 10))

    def _set_due_days(self, days: int) -> None:
        self.form_vars["due_date"].set((date.today() + timedelta(days=days)).isoformat())

    def _refresh_all(self) -> None:
        self._refresh_metrics()
        self._refresh_table()

    def _refresh_metrics(self) -> None:
        stats = self.store.stats()
        self.metric_vars["total"].set(str(stats.total_projects))
        self.metric_vars["active"].set(str(stats.active_projects))
        self.metric_vars["deadline"].set(str(stats.due_soon + stats.overdue))
        self.metric_vars["unpaid"].set(format_yen(stats.unpaid_amount))
        self.metric_vars["paid"].set(format_yen(stats.paid_amount))

    def _refresh_table(self) -> None:
        if not hasattr(self, "table"):
            return
        self._is_refreshing = True
        current = str(self.selected_id) if self.selected_id is not None else ""
        for item_id in self.table.get_children():
            self.table.delete(item_id)

        rows = self.store.list_projects(
            search=self.search_var.get(),
            status_filter=self.status_filter_var.get(),
            due_filter=self.due_filter_var.get(),
        )
        for row in rows:
            item_id = str(row["id"])
            self.table.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    row.get("title", ""),
                    row.get("client", ""),
                    row.get("status", ""),
                    describe_due(str(row.get("due_date", ""))),
                    row.get("invoice_state", ""),
                    row.get("payment_state", ""),
                    format_yen(row.get("amount", 0)),
                ),
                tags=(self._row_tag(row),),
            )

        if current and self.table.exists(current):
            self.table.selection_set(current)
            self.table.focus(current)
            self.table.see(current)
        self._is_refreshing = False
        self.status_text.set(f"{len(rows)}件表示 / DB {self.store.db_path}")

    def _row_tag(self, row: dict[str, object]) -> str:
        status = str(row.get("status", ""))
        days = days_until(str(row.get("due_date", "")))
        if status not in FINAL_STATUSES and days is not None:
            if days < 0:
                return "overdue"
            if days <= 7:
                return "soon"
        if row.get("payment_state") == "入金済":
            return "paid"
        if status in FINAL_STATUSES:
            return "final"
        return "normal"

    def _on_select(self, _event: tk.Event) -> None:
        if self._is_refreshing:
            return
        selection = self.table.selection()
        if not selection:
            return
        project = self.store.get_project(int(selection[0]))
        if project:
            self._load_project(project)

    def _load_project(self, project: dict[str, object]) -> None:
        self.selected_id = int(project["id"])
        for key in self.form_vars:
            self.form_vars[key].set(str(project.get(key, "")))
        self.memo_text.delete("1.0", "end")
        self.memo_text.insert("1.0", str(project.get("memo", "")))
        self.status_text.set(f"編集中 #{self.selected_id} / DB {self.store.db_path}")

    def _new_project(self) -> None:
        self.selected_id = None
        defaults = {
            "title": "",
            "client": "",
            "status": STATUSES[0],
            "due_date": "",
            "amount": "0",
            "invoice_state": INVOICE_STATES[0],
            "payment_state": PAYMENT_STATES[0],
        }
        for key, value in defaults.items():
            self.form_vars[key].set(value)
        if hasattr(self, "memo_text"):
            self.memo_text.delete("1.0", "end")
        if hasattr(self, "table"):
            self.table.selection_remove(self.table.selection())
        self.status_text.set(f"新規案件 / DB {self.store.db_path}")

    def _form_payload(self) -> dict[str, object]:
        return {
            **{key: variable.get() for key, variable in self.form_vars.items()},
            "memo": self.memo_text.get("1.0", "end").strip(),
        }

    def _save_project(self) -> None:
        try:
            saved_id = self.store.save_project(self._form_payload(), self.selected_id)
        except ValueError as exc:
            messagebox.showerror("保存できません", str(exc), parent=self)
            return

        self.selected_id = saved_id
        self._refresh_all()
        if self.table.exists(str(saved_id)):
            self.table.selection_set(str(saved_id))
            self.table.focus(str(saved_id))
            self.table.see(str(saved_id))
        self.status_text.set(f"保存しました #{saved_id}")
        self._check_deadline_notifications(force=False, reschedule=False)

    def _delete_project(self) -> None:
        if self.selected_id is None:
            messagebox.showinfo("削除", "削除する案件を選択してください。", parent=self)
            return
        if not messagebox.askyesno("削除", "選択中の案件を削除しますか？", parent=self):
            return
        deleted_id = self.selected_id
        self.store.delete_project(deleted_id)
        self._new_project()
        self._refresh_all()
        self.status_text.set(f"削除しました #{deleted_id}")

    def _export_csv(self) -> None:
        rows = self.store.list_projects(
            search=self.search_var.get(),
            status_filter=self.status_filter_var.get(),
            due_filter=self.due_filter_var.get(),
        )
        default_name = f"freelaboard_export_{date.today():%Y%m%d}.csv"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="CSV出力",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=(("CSV", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return
        count = self.store.export_csv(path, rows)
        messagebox.showinfo("CSV出力", f"{count}件を出力しました。", parent=self)
        self.status_text.set(f"CSV出力 {path}")

    def _on_notifications_toggle(self) -> None:
        self.store.set_bool_setting("deadline_notifications", self.notifications_var.get())
        self._sync_tray_icon()
        if self.notifications_var.get():
            self._check_deadline_notifications(force=True, reschedule=False)
        self.status_text.set("期限通知を更新しました")

    def _on_resident_toggle(self) -> None:
        self.store.set_bool_setting("resident_on_close", self.resident_var.get())
        self._sync_tray_icon()
        self.status_text.set("常駐設定を更新しました")

    def _save_notification_days(self) -> None:
        text = self.notification_days_var.get().strip()
        if not text:
            return
        try:
            days = max(1, min(30, int(text)))
        except ValueError:
            return
        if str(days) != text:
            self.notification_days_var.set(str(days))
            return
        self.store.set_setting("notification_days", str(days))

    def _notification_days(self) -> int:
        try:
            return max(1, min(30, int(self.notification_days_var.get())))
        except ValueError:
            self.notification_days_var.set("7")
            return 7

    def _check_deadline_notifications(
        self, force: bool = False, reschedule: bool = True
    ) -> None:
        if self._deadline_after:
            try:
                self.after_cancel(self._deadline_after)
            except tk.TclError:
                pass
            self._deadline_after = None

        if self.notifications_var.get():
            rows = self.store.due_alert_projects(self._notification_days())
            if rows:
                signature = deadline_notice_signature(rows)
                if force or signature != self.store.get_setting("last_deadline_notice", ""):
                    self.store.set_setting("last_deadline_notice", signature)
                    title, message, warning = self._deadline_message(rows)
                    if not self._show_desktop_notice(title, message, warning):
                        self._show_local_toast(title, message, warning)
            elif force:
                self._show_local_toast("期限通知", "通知対象の案件はありません。", False)

        if reschedule:
            self._deadline_after = self.after(
                CHECK_INTERVAL_MS,
                lambda: self._check_deadline_notifications(force=False),
            )

    def _deadline_message(self, rows: list[dict[str, object]]) -> tuple[str, str, bool]:
        overdue = sum(1 for row in rows if int(row.get("days_until", 0)) < 0)
        title = f"納期アラート {len(rows)}件"
        snippets: list[str] = []
        for row in rows[:4]:
            days = int(row.get("days_until", 0))
            if days < 0:
                due_label = f"{abs(days)}日超過"
            elif days == 0:
                due_label = "今日"
            else:
                due_label = f"あと{days}日"
            snippets.append(f"{row.get('title', '')}: {due_label}")
        if len(rows) > 4:
            snippets.append(f"ほか{len(rows) - 4}件")
        return title, "\n".join(snippets), overdue > 0

    def _show_desktop_notice(self, title: str, message: str, warning: bool) -> bool:
        return self.notifier.show_balloon(title, message, warning)

    def _show_local_toast(self, title: str, message: str, warning: bool) -> None:
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg=PALETTE["red"] if warning else PALETTE["cyan"])
        width = 390
        height = 136
        x = max(0, toast.winfo_screenwidth() - width - 28)
        y = max(0, toast.winfo_screenheight() - height - 68)
        toast.geometry(f"{width}x{height}+{x}+{y}")
        inner = tk.Frame(toast, bg=PALETTE["deck"], padx=14, pady=12)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(
            inner,
            text=title,
            bg=PALETTE["deck"],
            fg=PALETTE["red"] if warning else PALETTE["cyan"],
            font=("Yu Gothic UI", 12, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            inner,
            text=message,
            bg=PALETTE["deck"],
            fg=PALETTE["text"],
            justify="left",
            anchor="nw",
            font=("Yu Gothic UI", 10),
        ).pack(fill="both", expand=True, pady=(8, 0))
        toast.after(9000, toast.destroy)

    def _sync_tray_icon(self) -> None:
        if not hasattr(self, "notifier"):
            return
        if self.notifications_var.get() or self.resident_var.get():
            self.notifier.ensure_icon()
        elif not self._hidden_resident:
            self.notifier.close()

    def _on_close(self) -> None:
        if self._force_exit or not self.resident_var.get():
            self._exit_app()
            return
        if self.notifier.ensure_icon():
            self._hidden_resident = True
            self.withdraw()
            self.notifier.show_balloon(
                "FreelaBoard 常駐中",
                "期限通知を監視しています。アイコンをクリックすると復帰します。",
                False,
            )
        else:
            self.iconify()

    def _restore_from_resident(self) -> None:
        self.after(0, self._restore_window)

    def _exit_from_tray(self) -> None:
        self.after(0, self._exit_app)

    def _restore_window(self) -> None:
        self._hidden_resident = False
        self.deiconify()
        try:
            self.state("normal")
        except tk.TclError:
            pass
        self.lift()
        self.focus_force()

    def _exit_app(self) -> None:
        self._force_exit = True
        if self._deadline_after:
            try:
                self.after_cancel(self._deadline_after)
            except tk.TclError:
                pass
            self._deadline_after = None
        if hasattr(self, "notifier"):
            self.notifier.close()
        self.destroy()


def run() -> None:
    app = FreelaBoardApp()
    app.mainloop()
