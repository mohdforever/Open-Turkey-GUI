import os
import sqlite3
import subprocess
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

DB_PATH = "/var/lib/open-turkey/open-turkey.db"
SITE_COLS = ("domain", "site", "url", "host", "name")
APP_COLS = ("app", "process", "executable", "command", "name")


class OpenTurkeyGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Open Turkey Manager")
        self.root.geometry("600x580")
        self.root.configure(padx=15, pady=15)

        header_frame = ttk.Frame(root)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(header_frame, text="Open Turkey Blocker", font=("Sans", 14, "bold")).pack(side=tk.LEFT)
        ttk.Button(header_frame, text="Refresh", command=self.refresh_data).pack(side=tk.RIGHT)

        ttk.Label(root, text="Active Status, Blocks, Sites & Apps:", font=("Sans", 10, "bold")).pack(anchor=tk.W)
        self.output_text = tk.Text(
            root, height=16, width=68, state=tk.DISABLED, bg="#f4f4f4", font=("Monospace", 9)
        )
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=(5, 15))

        controls_frame = ttk.LabelFrame(root, text="Block Actions", padding=10)
        controls_frame.pack(fill=tk.X, pady=(0, 10))

        # Block selector dropdown row
        selector_row = ttk.Frame(controls_frame)
        selector_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(selector_row, text="Target Block:", font=("Sans", 10, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        self.block_var = tk.StringVar()
        self.block_combo = ttk.Combobox(selector_row, textvariable=self.block_var, state="normal")
        self.block_combo.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # Row 1: Start / Stop
        row1 = ttk.Frame(controls_frame)
        row1.pack(fill=tk.X, pady=3)
        ttk.Button(row1, text="▶ Start Block", command=self.start_block).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(row1, text="🔒 Start Locked", command=lambda: self.start_block(lock=True)).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=2
        )
        ttk.Button(row1, text="⏹ Stop Block", command=self.stop_block).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # Row 2: Create / Delete / Add Rules
        row2 = ttk.Frame(controls_frame)
        row2.pack(fill=tk.X, pady=3)
        ttk.Button(row2, text="+ New Block", command=self.create_block).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(row2, text="🗑 Delete Block", command=self.delete_block).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(row2, text="+ Add Website", command=self.add_site).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(row2, text="+ Add App", command=self.add_app).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.refresh_data()

    def run_cmd(self, args, timeout=15):
        """Executes `open-turkey <args>` directly and returns (success, message)."""
        try:
            result = subprocess.run(
                ["open-turkey"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return False, "Error: 'open-turkey' command not found."
        except PermissionError:
            return False, "Error: Permission denied running 'open-turkey'."
        except subprocess.TimeoutExpired:
            return False, f"Error: Command timed out after {timeout}s."

        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}"
            return False, f"Error:\n{err}"

        return True, result.stdout.strip() or "Done."

    @staticmethod
    def _pick_value_index(cursor, table_name, preferred_cols):
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = [info[1].lower() for info in cursor.fetchall()]
        for candidate in preferred_cols:
            if candidate in cols:
                return cols.index(candidate)
        return len(cols) - 1 if cols else 0

    def _open_readonly_db(self):
        if os.path.exists(DB_PATH) and os.access(DB_PATH, os.R_OK):
            try:
                return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            except sqlite3.Error:
                return None
        return None

    def get_block_names(self):
        """Returns a list of known block names from SQLite or CLI output."""
        conn = self._open_readonly_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blocks';")
                if cur.fetchone():
                    cur.execute("SELECT name FROM blocks ORDER BY name")
                    names = [str(r[0]) for r in cur.fetchall() if r[0]]
                    conn.close()
                    return names
            except sqlite3.Error:
                pass
            finally:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

        ok, raw_list = self.run_cmd(["block", "list"])
        if not ok or not raw_list:
            return []

        names = []
        for line in raw_list.splitlines():
            clean = line.strip().strip("│").strip().lstrip("-•* ")
            if not clean or clean[0] in ("─", "=", "┌", "├", "└"):
                continue
            lower = clean.lower()
            if lower.startswith("name") or lower.startswith("id"):
                continue
            names.append(clean.split()[0])
        return names

    def get_detailed_blocks(self, block_names=None):
        """Fetches blocks, sites, and apps from SQLite DB or CLI fallback."""
        conn = self._open_readonly_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = {row[0] for row in cur.fetchall()}

                if "blocks" in tables:
                    cur.execute("SELECT id, name FROM blocks ORDER BY name")
                    blocks = cur.fetchall()
                    if not blocks:
                        conn.close()
                        return "No blocks configured yet."

                    site_table = next((t for t in ("block_sites", "sites", "domains") if t in tables), None)
                    app_table = next((t for t in ("block_apps", "apps", "applications") if t in tables), None)

                    site_idx = self._pick_value_index(cur, site_table, SITE_COLS) if site_table else 0
                    app_idx = self._pick_value_index(cur, app_table, APP_COLS) if app_table else 0

                    lines = []
                    for b_id, b_name in blocks:
                        lines.append(f"• Block: {b_name}")

                        if site_table:
                            cur.execute(f"SELECT * FROM {site_table} WHERE block_id = ?", (b_id,))
                            sites = [str(r[site_idx]) for r in cur.fetchall() if len(r) > site_idx]
                            lines.append(f"    Sites: {', '.join(sites) if sites else 'None'}")

                        if app_table:
                            cur.execute(f"SELECT * FROM {app_table} WHERE block_id = ?", (b_id,))
                            apps = [str(r[app_idx]) for r in cur.fetchall() if len(r) > app_idx]
                            lines.append(f"    Apps:  {', '.join(apps) if apps else 'None'}")

                    conn.close()
                    return "\n".join(lines)
            except sqlite3.Error:
                pass
            finally:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass

        names = block_names if block_names is not None else self.get_block_names()
        if not names:
            return "No blocks configured yet."

        output_lines = []
        for block_name in names:
            _, details = self.run_cmd(["block", "show", block_name])
            output_lines.append(f"• {block_name}\n{details}\n")
        return "\n".join(output_lines)

    def _refresh_dropdown(self, names):
        current = self.block_var.get().strip()
        self.block_combo["values"] = names
        if current in names:
            self.block_var.set(current)
        elif names:
            self.block_var.set(names[0])
        else:
            self.block_var.set("")

    def _selected_block(self):
        name = self.block_var.get().strip()
        if not name:
            messagebox.showwarning("No Block Selected", "Select or enter a block name first.")
            return ""
        return name

    def update_display(self, text):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, text)
        self.output_text.config(state=tk.DISABLED)

    def refresh_data(self):
        _, status = self.run_cmd(["status"])
        names = self.get_block_names()
        self._refresh_dropdown(names)
        detailed_blocks = self.get_detailed_blocks(block_names=names)
        display_str = f"=== STATUS ===\n{status}\n\n=== CONFIGURED BLOCKS & RULES ===\n{detailed_blocks}"
        self.update_display(display_str)

    def _ask_non_empty(self, title, prompt):
        val = simpledialog.askstring(title, prompt)
        return val.strip() if val else ""

    def start_block(self, lock=False):
        name = self._selected_block()
        if name:
            cmd = ["start", name]
            if lock:
                cmd.append("--lock")
            _, res = self.run_cmd(cmd)
            messagebox.showinfo("Open Turkey", res)
            self.refresh_data()

    def stop_block(self):
        name = self._selected_block()
        if name:
            _, res = self.run_cmd(["stop", name])
            messagebox.showinfo("Open Turkey", res)
            self.refresh_data()

    def create_block(self):
        name = self._ask_non_empty("Create Block", "Enter a name for the new block (e.g., work):")
        if name:
            _, res = self.run_cmd(["block", "create", name])
            if res and not res.startswith("Error:"):
                self.block_var.set(name)
            messagebox.showinfo("Open Turkey", res)
            self.refresh_data()

    def delete_block(self):
        name = self._selected_block()
        if not name:
            return
        confirmed = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete block '{name}' and its rules?",
        )
        if not confirmed:
            return
        _, res = self.run_cmd(["block", "delete", name])
        if self.block_var.get().strip() == name:
            self.block_var.set("")
        messagebox.showinfo("Open Turkey", res)
        self.refresh_data()

    def add_site(self):
        name = self._selected_block()
        if not name:
            return
        site = self._ask_non_empty("Add Website", f"Enter domain to block in '{name}' (e.g., reddit.com):")
        if site:
            _, res = self.run_cmd(["block", "add-site", name, site])
            messagebox.showinfo("Open Turkey", res)
            self.refresh_data()

    def add_app(self):
        name = self._selected_block()
        if not name:
            return
        app = self._ask_non_empty("Add App", f"Enter process/app name to block in '{name}' (e.g., discord):")
        if app:
            _, res = self.run_cmd(["block", "add-app", name, app])
            messagebox.showinfo("Open Turkey", res)
            self.refresh_data()


if __name__ == "__main__":
    root = tk.Tk()
    app = OpenTurkeyGUI(root)
    root.mainloop()
