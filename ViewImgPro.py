# -*- coding: utf-8 -*-
r"""ViewImgPro - fast image review, filtering and zoom-crop for Windows.

Install: py -m pip install Pillow
Run:     py viewimgpro.py

Select a parent folder or a single image folder. The tool scans directories recursively
for image files, so source video files are not needed. Example:
F:\Downloads\img\IMG_Khach\IMG_4759\frame_0001.jpg
Selected images are COPIED to the matching folder's "Đã lọc hình" subfolder.
"Copy cắt theo khung zoom" saves each selected image cropped to the region currently shown
in the viewer (same zoom level and position) as <name>_crop.<ext> in the same "Đã lọc hình" folder.
Original files are never moved or deleted.
"""
from __future__ import annotations

import os
import math
import queue
import re
import shutil
import subprocess
import tempfile
import time
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
except ImportError:
    raise SystemExit("Chưa cài Pillow. Mở CMD và chạy: py -m pip install Pillow")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


class VideoImageFilterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ViewImgPro - Xem, chọn lọc và cắt khung hình")
        self.root.geometry("1450x900")
        self.root.minsize(1080, 650)
        self._maximize_window()

        self.root_dir: Path | None = None
        # Directories containing images are discovered from the filesystem; no video file is required.
        self.video_dirs: list[Path] = []
        self.folder_labels: list[str] = []
        self.current_dir: Path | None = None
        self.image_paths: list[Path] = []
        self.path_to_index: dict[Path, int] = {}
        self.selected: set[Path] = set()
        self._selected_here_count = 0
        self.current_image: Path | None = None

        # --- Image viewer state -------------------------------------------------
        # The canvas always shows ONE viewport-sized frame (see "Image viewer" section below),
        # so zoom/pan cost depends on the window size, never on the photo size.
        self.original_image: Image.Image | None = None
        self._pyramid: list[tuple[int, Image.Image]] = []   # [(downscale factor, image)], level 0 = original
        self.tk_image = None
        self._canvas_image_id = None
        self._frame_size = (0, 0)
        self.zoom = 1.0                 # Native-pixel scale: 1.5 means 150%.
        self.fit_mode = True
        self.fit_scale = 1.0
        self.cur_scale = 1.0            # scale currently on screen (differs from zoom while animating)
        self.view_cx = 0.0              # view centre in source-image pixels
        self.view_cy = 0.0
        self._zoom_target = 1.0
        self._zoom_anchor = (0.0, 0.0)
        self._zoom_anim_id = None
        self._zoom_last_t = 0.0
        self._draw_pending = False
        self._hq_after_id = None
        self._drag_last = None
        self._label_text = ""
        self._render_token = 0
        self._render_queue: queue.Queue = queue.Queue()
        self._render_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-render")
        self._render_future = None
        self._busy_message = ""
        self._checkbox_images = {}
        self.ffmpeg_path: Path | None = self._load_saved_ffmpeg_path()

        self._build_ui()
        # Space and Enter both toggle the checkbox of the image currently being viewed:
        # first press selects; the next press deselects.
        self.root.bind_all("<space>", self._space_shortcut)
        self.root.bind_all("<Return>", self._enter_shortcut)
        self.root.bind_all("<KP_Enter>", self._enter_shortcut)
        self.root.bind_all("<Left>", lambda _e: self.show_relative_image(-1))
        self.root.bind_all("<Right>", lambda _e: self.show_relative_image(1))
        self.root.bind_all("<Control-o>", lambda _e: self.choose_root())
        self.root.bind_all("<Control-plus>", lambda _e: self.zoom_by(1.2))
        self.root.bind_all("<Control-equal>", lambda _e: self.zoom_by(1.2))
        self.root.bind_all("<Control-minus>", lambda _e: self.zoom_by(1 / 1.2))
        self.root.after(25, self._poll_render_queue)

    def _maximize_window(self):
        """Open the app maximized (full screen area, keeps title bar and taskbar)."""
        try:
            self.root.state("zoomed")            # Windows / macOS
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)   # Linux
            except tk.TclError:
                self.root.geometry(
                    f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0"
                )

    def _build_ui(self):
        style = ttk.Style()
        try:
            if "vista" in style.theme_names():
                style.theme_use("vista")
        except tk.TclError:
            pass
        # Keep rows compact enough to show more frames at once, while checkbox icons remain large.
        style.configure("ImageList.Treeview", font=("Segoe UI", 10), rowheight=32)
        style.configure("ImageList.Treeview", background="#ffffff", fieldbackground="#ffffff")
        style.map("ImageList.Treeview", background=[("selected", "#cfe8ff")], foreground=[("selected", "#102a43")])
        style.configure("Tool.TButton", font=("Segoe UI", 10), padding=(8, 5))
        # Make the split handle easy to notice and drag between the list and preview.
        style.configure("Wide.TPanedwindow", sashwidth=9, sashrelief="raised")

        # Large, crisp checkbox icons. Updating a selection changes only one Treeview row.
        self._checkbox_images[False] = self._make_checkbox(False)
        self._checkbox_images[True] = self._make_checkbox(True)

        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(top, text="📂 Chọn thư mục gốc", style="Tool.TButton", command=self.choose_root).pack(side=tk.LEFT)
        self.root_label = ttk.Label(top, text="Chưa chọn thư mục", anchor="w", font=("Segoe UI", 10))
        self.root_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        ttk.Button(top, text="Video → IMG", style="Tool.TButton", command=self.open_video_to_img_dialog).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(top, text="⟳ Tải lại", style="Tool.TButton", command=self.refresh_root).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(top, text="Copy ảnh đã chọn", style="Tool.TButton", command=self.copy_selected).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(top, text="✂ Copy cắt theo khung zoom", style="Tool.TButton",
                   command=self.copy_selected_cropped).pack(side=tk.RIGHT, padx=(5, 0))

        main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL, style="Wide.TPanedwindow")
        self.main_pane = main
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # LEFT: intentionally narrower by default; drag the sash to resize either pane.
        left = ttk.Frame(main, padding=8, width=360)
        main.add(left, weight=0)
        ttk.Label(left, text="THƯ MỤC ẢNH", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        folder_frame = ttk.Frame(left)
        folder_frame.pack(fill=tk.X, pady=(5, 8))
        self.folder_list = tk.Listbox(
            folder_frame, height=4, exportselection=False,
            font=("Segoe UI", 10), activestyle="dotbox",
            selectbackground="#cfe8ff", selectforeground="#102a43",
            highlightthickness=1, relief=tk.FLAT
        )
        folder_scroll = ttk.Scrollbar(folder_frame, orient=tk.VERTICAL, command=self.folder_list.yview)
        self.folder_list.configure(yscrollcommand=folder_scroll.set)
        self.folder_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        folder_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.folder_list.bind("<<ListboxSelect>>", self.on_folder_select)

        ttk.Separator(left).pack(fill=tk.X, pady=4)
        header = ttk.Frame(left)
        header.pack(fill=tk.X)
        ttk.Label(header, text="DANH SÁCH ẢNH", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.count_label = ttk.Label(header, text="0 ảnh | 0 chọn", font=("Segoe UI", 9))
        self.count_label.pack(side=tk.RIGHT)

        # Selection actions are split into two compact rows to fit the narrow left pane.
        actions = ttk.Frame(left)
        actions.pack(fill=tk.X, pady=(7, 6))
        actions_row1 = ttk.Frame(actions)
        actions_row1.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(
            actions_row1, text="✓ Chọn tất cả", style="Tool.TButton", command=self.select_all
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            actions_row1, text="Bỏ chọn tất cả", style="Tool.TButton", command=self.deselect_all
        ).pack(side=tk.LEFT)
        actions_row2 = ttk.Frame(actions)
        actions_row2.pack(fill=tk.X)
        ttk.Button(
            actions_row2, text="Bỏ chọn ảnh đang xem", style="Tool.TButton", command=self.deselect_current
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(
            actions_row2, text="Space / Enter: chọn-bỏ chọn", foreground="#4b5563"
        ).pack(side=tk.RIGHT)

        list_container = ttk.Frame(left)
        list_container.pack(fill=tk.BOTH, expand=True)
        # Use ONLY the tree column. A previous version also populated a filename
        # data column, which caused the same filename to appear twice in some themes.
        self.image_tree = ttk.Treeview(
            list_container, show="tree", selectmode="browse", style="ImageList.Treeview"
        )
        self.image_tree.column("#0", width=310, minwidth=180, stretch=True, anchor="w")
        tree_scroll = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.image_tree.yview)
        self.image_tree.configure(yscrollcommand=tree_scroll.set)
        self.image_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_tree.bind("<<TreeviewSelect>>", self.on_image_select)
        self.image_tree.bind("<Button-1>", self.on_tree_click, add=True)

        self.selected_label = ttk.Label(left, text="Tổng ảnh đã chọn: 0", foreground="#176b35", font=("Segoe UI", 10, "bold"))
        self.selected_label.pack(anchor="w", pady=(7, 0))
        ttk.Label(
            left,
            text="Ảnh đã chọn sẽ được copy vào thư mục con ‘Đã lọc hình’ của từng thư mục video.",
            wraplength=360, foreground="#4b5563", font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(4, 0))

        # RIGHT: image preview and zoom controls.
        right = ttk.Frame(main, padding=8)
        main.add(right, weight=1)
        # Set a compact initial split once Tk has calculated the actual window size.
        self.root.after(180, self._set_initial_sash)
        toolbar = ttk.Frame(right)
        toolbar.pack(fill=tk.X, pady=(0, 7))
        self.current_label = ttk.Label(toolbar, text="Chọn ảnh để xem", font=("Segoe UI", 10, "bold"))
        self.current_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(toolbar, text="Xoay trái", command=lambda: self.rotate_image(-90)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="Xoay phải", command=lambda: self.rotate_image(90)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="Ảnh thật 1:1", command=self.view_actual_size).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="Vừa khung", command=self.fit_image).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="−", width=3, command=lambda: self.zoom_by(1 / 1.2)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(toolbar, text="+", width=3, command=lambda: self.zoom_by(1.2)).pack(side=tk.RIGHT, padx=2)

        canvas_frame = ttk.Frame(right)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(canvas_frame, background="#202124", highlightthickness=0, cursor="fleur")
        self.hbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self._xview_command)
        self.vbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self._yview_command)
        self.canvas.configure(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<MouseWheel>", self._mouse_wheel)
        self.canvas.bind("<Control-MouseWheel>", self._mouse_zoom)
        self.canvas.bind("<ButtonPress-1>", self._pan_start)
        self.canvas.bind("<B1-Motion>", self._pan_move)
        self.canvas.bind("<ButtonRelease-1>", self._pan_end)
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        self.status = ttk.Label(self.root, text="Sẵn sàng", relief=tk.SUNKEN, anchor="w", padding=(8, 4))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _set_initial_sash(self):
        """Start with a compact left list; users can drag the sash afterward."""
        try:
            # Tk coordinates are logical pixels; Windows display scaling is handled by Tk.
            self.main_pane.sashpos(0, 365)
        except tk.TclError:
            pass

    @staticmethod
    def _make_checkbox(checked: bool):
        size = 25
        img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
        d = ImageDraw.Draw(img)
        if checked:
            d.rounded_rectangle((2, 2, size - 3, size - 3), radius=4, fill="#1677d2", outline="#0d5ca8", width=2)
            d.line((6, 13, 10, 17, 19, 7), fill="white", width=3, joint="curve")
        else:
            d.rounded_rectangle((2, 2, size - 3, size - 3), radius=4, fill="#ffffff", outline="#667085", width=2)
        return ImageTk.PhotoImage(img)

    def choose_root(self):
        chosen = filedialog.askdirectory(title="Chọn thư mục gốc để quét các thư mục ảnh")
        if chosen:
            self.root_dir = Path(chosen)
            self.refresh_root()

    def refresh_root(self):
        if not self.root_dir or not self.root_dir.exists():
            return
        self.root_label.config(text=str(self.root_dir))
        # Scan the directory tree, not the list of source videos. This also works
        # when the original .MOV/.MP4 file has been moved or deleted. Every folder
        # that directly contains images becomes a browseable entry; nested folders
        # are scanned independently. Output folders "Đã lọc hình" (and "Đã lọc hình_zoom" from an earlier version) are excluded.
        filtered_names = {"đã lọc hình".casefold(), "đã lọc hình_zoom".casefold()}
        found_folders: list[Path] = []
        for current, dirnames, filenames in os.walk(self.root_dir):
            current_path = Path(current)
            if current_path.name.casefold() in filtered_names:
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if name.casefold() not in filtered_names]
            if any(Path(filename).suffix.lower() in IMAGE_EXTS for filename in filenames):
                found_folders.append(current_path)

        self.video_dirs = sorted(found_folders, key=lambda p: str(p).casefold())
        self.folder_labels = []
        for folder in self.video_dirs:
            if folder == self.root_dir:
                label = f"{folder.name}  [thư mục gốc]"
            else:
                try:
                    label = str(folder.relative_to(self.root_dir))
                except ValueError:
                    label = folder.name
            self.folder_labels.append(label)

        self.folder_list.delete(0, tk.END)
        for label in self.folder_labels:
            self.folder_list.insert(tk.END, label)
        if self.video_dirs:
            self.folder_list.selection_clear(0, tk.END)
            self.folder_list.selection_set(0)
            self.folder_list.activate(0)
            self.load_video_folder(self.video_dirs[0])
        else:
            self.current_dir = None
            self.image_paths = []
            self.image_tree.delete(*self.image_tree.get_children())
            self.clear_viewer()
            self.update_counts()
        self.status.config(text=f"Quét thư mục hoàn tất: tìm thấy {len(self.video_dirs)} thư mục có ảnh.")

    def on_folder_select(self, _event=None):
        selection = self.folder_list.curselection()
        if selection and selection[0] < len(self.video_dirs):
            self.load_video_folder(self.video_dirs[selection[0]])

    def load_video_folder(self, folder: Path):
        self.current_dir = folder
        self.image_paths = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS],
            key=lambda p: p.name.lower()
        )
        self.path_to_index = {path: index for index, path in enumerate(self.image_paths)}
        self._selected_here_count = sum(1 for p in self.image_paths if p in self.selected)
        # A Treeview row is inserted once; a tick updates only that row, not the full list.
        self.image_tree.delete(*self.image_tree.get_children())
        for index, path in enumerate(self.image_paths):
            self.image_tree.insert(
                "", tk.END, iid=str(index), text=path.name,
                image=self._checkbox_images[path in self.selected]
            )
        self.update_counts()
        if self.image_paths:
            self.image_tree.selection_set("0")
            self.image_tree.focus("0")
            self.image_tree.see("0")
            self.display_image(self.image_paths[0])
        else:
            self.clear_viewer()
            self.current_label.config(text=f"{folder.name} — không có ảnh")
        self.status.config(text=f"{folder.name}: {len(self.image_paths)} ảnh")

    def on_tree_click(self, event):
        # A click on the large checkbox selects that row as the current preview too,
        # so Space/Enter and the "Bỏ chọn ảnh đang xem" button always target the same image.
        row = self.image_tree.identify_row(event.y)
        if not row:
            return
        element = self.image_tree.identify_element(event.x, event.y)
        if event.x <= 34 or "image" in element.lower():
            try:
                idx = int(row)
            except ValueError:
                return "break"
            if 0 <= idx < len(self.image_paths):
                path = self.image_paths[idx]
                self.image_tree.selection_set(row)
                self.image_tree.focus(row)
                self.image_tree.focus_set()
                self.display_image(path)
                self.toggle_path(path)
            return "break"

    def on_image_select(self, _event=None):
        selection = self.image_tree.selection()
        if not selection:
            return
        try:
            index = int(selection[0])
        except ValueError:
            return
        if 0 <= index < len(self.image_paths):
            self.display_image(self.image_paths[index])

    def toggle_path(self, path: Path):
        if path in self.selected:
            self.selected.remove(path)
            checked = False
            if self.current_dir and path.parent == self.current_dir:
                self._selected_here_count = max(0, self._selected_here_count - 1)
        else:
            self.selected.add(path)
            checked = True
            if self.current_dir and path.parent == self.current_dir:
                self._selected_here_count += 1
        # The critical performance fix: update one Treeview row, O(1), instead of
        # deleting/reinserting every image row on every checkbox toggle.
        if self.current_dir and path.parent == self.current_dir:
            try:
                idx = self.path_to_index[path]
                self.image_tree.item(str(idx), image=self._checkbox_images[checked])
            except (ValueError, tk.TclError):
                pass
        self.update_counts()

    # ------------------------------------------------------------------
    # Image viewer
    # ------------------------------------------------------------------
    # Design (why zoom/pan are smooth):
    #  * The canvas shows exactly ONE viewport-sized frame. Each frame is produced by resizing
    #    only the visible region of the photo, so cost depends on the window, not on the photo.
    #  * A mip pyramid (1/2, 1/4, 1/8 ...) is built once when the image loads, so zooming out
    #    never has to resample a 20-30 MP image.
    #  * While the user is interacting we use fast resampling; ~140 ms after the last change a
    #    high-quality frame replaces it.
    #  * Zoom is animated (exponential easing) and anchored on the mouse pointer.
    #  * One PhotoImage is reused (paste) instead of creating a new one every frame.
    CANVAS_BG = (0x20, 0x21, 0x24)
    MIN_ZOOM = 0.05
    MAX_ZOOM = 8.0

    def display_image(self, path: Path):
        if path == self.current_image:
            return
        center = self._center_fraction()
        self.current_image = path
        self._label_text = ""
        self.current_label.config(text=f"Đang tải: {path.name}…")
        self.status.config(text=f"Đang mở ảnh: {path.name}")
        self._request_load(path, center)

    # ---- loading -------------------------------------------------------
    @staticmethod
    def _build_pyramid(image: Image.Image):
        levels = [(1, image)]
        current, factor = image, 1
        while min(current.size) >= 1024:
            current = current.reduce(2)
            factor *= 2
            levels.append((factor, current))
        return levels

    def _request_load(self, path: Path, center):
        self._render_token += 1
        token = self._render_token
        if self._render_future is not None:
            self._render_future.cancel()  # drop a queued load; a running one checks its token

        def worker():
            if token != self._render_token:
                return
            try:
                with Image.open(path) as opened:
                    original = ImageOps.exif_transpose(opened).convert("RGB")
                if token != self._render_token:
                    return
                levels = self._build_pyramid(original)
                self._render_queue.put((token, path, levels, None, center))
            except Exception as exc:
                self._render_queue.put((token, path, None, str(exc), center))

        self._render_future = self._render_executor.submit(worker)

    def _poll_render_queue(self):
        try:
            while True:
                token, path, levels, error, center = self._render_queue.get_nowait()
                if token != self._render_token or path != self.current_image:
                    continue
                if error:
                    self.status.config(text=f"Lỗi mở ảnh: {path.name}")
                    messagebox.showerror("Không mở được ảnh", f"{path}\n\n{error}")
                    continue
                self._set_image(levels, center)
                self.status.config(text=f"Đang xem: {path}")
        except queue.Empty:
            pass
        self.root.after(25, self._poll_render_queue)

    def _set_image(self, levels, center):
        self._cancel_zoom_animation()
        self._pyramid = levels
        self.original_image = levels[0][1]
        ow, oh = self.original_image.size
        self._update_fit_scale()
        self.cur_scale = self.fit_scale if self.fit_mode else self.zoom
        self._zoom_target = self.cur_scale
        self.view_cx = center[0] * ow
        self.view_cy = center[1] * oh
        self._draw_now(hq=True)

    # ---- geometry helpers ----------------------------------------------
    def _viewport(self):
        return max(self.canvas.winfo_width(), 1), max(self.canvas.winfo_height(), 1)

    def _center_fraction(self):
        if self.original_image is None:
            return (0.5, 0.5)
        ow, oh = self.original_image.size
        return (self.view_cx / max(ow, 1), self.view_cy / max(oh, 1))

    def _update_fit_scale(self):
        if self.original_image is None:
            return
        ow, oh = self.original_image.size
        cw, ch = self._viewport()
        self.fit_scale = min(cw / max(ow, 1), ch / max(oh, 1), 1.0)

    @staticmethod
    def _clamp_axis(center, size, view, scale):
        if size * scale <= view:
            return size / 2          # image smaller than the viewport: keep it centred
        half = view / (2 * scale)
        return min(max(center, half), size - half)

    def _clamp_view(self):
        ow, oh = self.original_image.size
        cw, ch = self._viewport()
        s = self.cur_scale
        self.view_cx = self._clamp_axis(self.view_cx, ow, cw, s)
        self.view_cy = self._clamp_axis(self.view_cy, oh, ch, s)

    # ---- rendering -----------------------------------------------------
    def _render_frame(self, hq: bool):
        """Return an RGB image exactly the size of the canvas showing the current view."""
        cw, ch = self._viewport()
        levels = self._pyramid
        if not levels:
            return Image.new("RGB", (cw, ch), self.CANVAS_BG)
        ow, oh = levels[0][1].size
        s = self.cur_scale
        # Position of the image's top-left corner inside the viewport (viewport pixels).
        left = cw / 2 - self.view_cx * s
        top = ch / 2 - self.view_cy * s
        dx0 = max(0, round(left))
        dy0 = max(0, round(top))
        dx1 = min(cw, round(left + ow * s))
        dy1 = min(ch, round(top + oh * s))
        dw, dh = dx1 - dx0, dy1 - dy0
        if dw <= 0 or dh <= 0:
            return Image.new("RGB", (cw, ch), self.CANVAS_BG)

        # Pick the smallest pyramid level that is still at least as large as the target.
        level = 0
        if s < 1.0:
            for index, (factor, _img) in enumerate(levels):
                if s * factor <= 1.0:
                    level = index
        factor, source = levels[level]
        sw, sh = source.size
        bx0 = max(0.0, (dx0 - left) / s / factor)
        by0 = max(0.0, (dy0 - top) / s / factor)
        bx1 = min(float(sw), (dx1 - left) / s / factor)
        by1 = min(float(sh), (dy1 - top) / s / factor)
        bx1 = max(bx1, min(float(sw), bx0 + 1e-3))
        by1 = max(by1, min(float(sh), by0 + 1e-3))
        if s >= 1.0:
            resample = Image.Resampling.BICUBIC if hq else Image.Resampling.BILINEAR
        else:
            resample = Image.Resampling.LANCZOS if hq else Image.Resampling.BILINEAR
        part = source.resize((dw, dh), resample, box=(bx0, by0, bx1, by1))
        if (dw, dh) == (cw, ch):
            return part
        frame = Image.new("RGB", (cw, ch), self.CANVAS_BG)
        frame.paste(part, (dx0, dy0))
        return frame

    def _present(self, frame: Image.Image):
        if self.tk_image is not None and self._frame_size == frame.size:
            self.tk_image.paste(frame)       # reuse the Tk image: no allocation, no flicker
            return
        self.tk_image = ImageTk.PhotoImage(frame)
        self._frame_size = frame.size
        if self._canvas_image_id is None:
            self._canvas_image_id = self.canvas.create_image(0, 0, image=self.tk_image, anchor=tk.NW)
        else:
            self.canvas.itemconfigure(self._canvas_image_id, image=self.tk_image)

    def _draw_now(self, hq: bool = False):
        if self.original_image is None:
            return
        self._clamp_view()
        self._present(self._render_frame(hq))
        self._update_scrollbars()
        self._update_label()
        if hq:
            self._cancel_hq()
        else:
            self._schedule_hq()

    def _request_draw(self):
        """Coalesce bursts of pan/scroll/resize events into one fast frame."""
        if self._draw_pending:
            return
        self._draw_pending = True
        self.root.after_idle(self._idle_draw)

    def _idle_draw(self):
        self._draw_pending = False
        self._draw_now(hq=False)

    def _schedule_hq(self):
        self._cancel_hq()
        self._hq_after_id = self.root.after(140, self._hq_pass)

    def _cancel_hq(self):
        if self._hq_after_id is not None:
            try:
                self.root.after_cancel(self._hq_after_id)
            except tk.TclError:
                pass
            self._hq_after_id = None

    def _hq_pass(self):
        self._hq_after_id = None
        if self.original_image is None or self._zoom_anim_id is not None:
            return
        self._present(self._render_frame(True))

    def _update_label(self):
        if self.current_image is None or self.original_image is None:
            return
        ow, oh = self.original_image.size
        zoom_text = "Vừa khung" if self.fit_mode else f"Zoom {round(self.cur_scale * 100)}%"
        text = f"{self.current_image.name}  |  {ow} × {oh}  |  {zoom_text}"
        if text != self._label_text:
            self._label_text = text
            self.current_label.config(text=text)

    def _update_scrollbars(self):
        ow, oh = self.original_image.size
        cw, ch = self._viewport()
        s = self.cur_scale
        for bar, size, view, center in ((self.hbar, ow * s, cw, self.view_cx),
                                        (self.vbar, oh * s, ch, self.view_cy)):
            if size <= view:
                bar.set(0.0, 1.0)
            else:
                first = (center * s - view / 2) / size
                bar.set(first, first + view / size)

    # ---- scrollbars ----------------------------------------------------
    def _xview_command(self, *args):
        self._scroll_command("x", args)

    def _yview_command(self, *args):
        self._scroll_command("y", args)

    def _scroll_command(self, axis, args):
        if self.original_image is None or not args:
            return
        ow, oh = self.original_image.size
        cw, ch = self._viewport()
        s = self.cur_scale
        size = (ow if axis == "x" else oh) * s
        view = cw if axis == "x" else ch
        if size <= view:
            return
        center = self.view_cx if axis == "x" else self.view_cy
        left = center * s - view / 2
        if args[0] == "moveto":
            left = float(args[1]) * size
        elif args[0] == "scroll":
            unit = view * 0.9 if args[2] == "pages" else max(30.0, view * 0.1)
            left += int(args[1]) * unit
        new_center = (left + view / 2) / s
        if axis == "x":
            self.view_cx = new_center
        else:
            self.view_cy = new_center
        self._request_draw()

    # ---- zoom ----------------------------------------------------------
    def _cancel_zoom_animation(self):
        if self._zoom_anim_id is not None:
            try:
                self.root.after_cancel(self._zoom_anim_id)
            except tk.TclError:
                pass
            self._zoom_anim_id = None

    def _zoom_to(self, target: float, anchor, fit: bool = False):
        """Animate to `target` scale, keeping the image point under `anchor` (viewport px) fixed."""
        if self.original_image is None:
            return
        target = max(self.MIN_ZOOM, min(self.MAX_ZOOM, target)) if not fit else target
        self.fit_mode = fit
        if not fit:
            self.zoom = target
        self._zoom_target = target
        self._zoom_anchor = anchor
        if self._zoom_anim_id is None:
            self._zoom_last_t = time.perf_counter()
            self._zoom_anim_id = self.root.after(1, self._zoom_step)

    def _zoom_step(self):
        self._zoom_anim_id = None
        if self.original_image is None:
            return
        now = time.perf_counter()
        dt = min(now - self._zoom_last_t, 0.1)
        self._zoom_last_t = now
        current, target = self.cur_scale, self._zoom_target
        alpha = 1.0 - math.exp(-dt / 0.055)          # time-based, so slow frames just skip ahead
        new = current * (target / current) ** alpha
        done = abs(math.log(target / new)) < 0.004
        if done:
            new = target
        self._scale_about(new, self._zoom_anchor)
        if done:
            self._draw_now(hq=True)                  # final frame in full quality
        else:
            self._draw_now(hq=False)
            self._zoom_anim_id = self.root.after(4, self._zoom_step)

    def _scale_about(self, new_scale: float, anchor):
        """Set the on-screen scale, keeping the source point under `anchor` (viewport px) fixed."""
        px, py = anchor
        cw, ch = self._viewport()
        current = self.cur_scale
        src_x = self.view_cx + (px - cw / 2) / current
        src_y = self.view_cy + (py - ch / 2) / current
        self.cur_scale = new_scale
        self.view_cx = src_x - (px - cw / 2) / new_scale
        self.view_cy = src_y - (py - ch / 2) / new_scale

    def _finish_zoom_animation(self):
        """Jump to the final zoom level if an animation is still running."""
        if self._zoom_anim_id is None:
            return
        self._cancel_zoom_animation()
        self._scale_about(self._zoom_target, self._zoom_anchor)
        self._draw_now(hq=True)

    def zoom_by(self, factor: float, anchor=None):
        if self.original_image is None:
            return
        if anchor is None:
            cw, ch = self._viewport()
            anchor = (cw / 2, ch / 2)
        base = self._zoom_target if self._zoom_anim_id is not None else self.cur_scale
        self._zoom_to(base * factor, anchor)

    def fit_image(self):
        if self.original_image is None:
            return
        self._update_fit_scale()
        cw, ch = self._viewport()
        self._zoom_to(self.fit_scale, (cw / 2, ch / 2), fit=True)

    def view_actual_size(self):
        if self.original_image is None:
            return
        cw, ch = self._viewport()
        self._zoom_to(1.0, (cw / 2, ch / 2))

    def rotate_image(self, degrees: int):
        if self.original_image is None or self.current_image is None:
            return
        self._cancel_zoom_animation()
        rotated = self.original_image.rotate(degrees, expand=True)
        self._pyramid = self._build_pyramid(rotated)
        self.original_image = rotated
        self.fit_mode = True
        self._update_fit_scale()
        self.cur_scale = self.fit_scale
        self._zoom_target = self.fit_scale
        ow, oh = rotated.size
        self.view_cx, self.view_cy = ow / 2, oh / 2
        self._draw_now(hq=True)

    def _on_canvas_resize(self, _event):
        if self.original_image is None:
            return
        self._update_fit_scale()
        if self.fit_mode:
            self._zoom_target = self.fit_scale
            if self._zoom_anim_id is None:
                self.cur_scale = self.fit_scale
        self._request_draw()

    # ---- mouse ---------------------------------------------------------
    def _pointer_in_canvas(self):
        """Pointer position in canvas pixels (reliable for wheel events on Windows)."""
        cw, ch = self._viewport()
        px = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx()
        py = self.canvas.winfo_pointery() - self.canvas.winfo_rooty()
        return (max(0, min(cw, px)), max(0, min(ch, py)))

    def _mouse_wheel(self, event):
        if self.original_image is None:
            return
        step = event.delta / 120 * 90 / max(self.cur_scale, 1e-6)   # ~90 screen px per notch
        if event.state & 0x0001:
            self.view_cx -= step
        else:
            self.view_cy -= step
        self._request_draw()

    def _mouse_zoom(self, event):
        self.zoom_by(1.2 ** (event.delta / 120), anchor=self._pointer_in_canvas())
        return "break"

    def _pan_start(self, event):
        self.canvas.focus_set()
        self._drag_last = (event.x, event.y)

    def _pan_move(self, event):
        if self._drag_last is None or self.original_image is None:
            return
        last_x, last_y = self._drag_last
        self._drag_last = (event.x, event.y)
        s = max(self.cur_scale, 1e-6)
        self.view_cx -= (event.x - last_x) / s
        self.view_cy -= (event.y - last_y) / s
        self._request_draw()

    def _pan_end(self, _event):
        self._drag_last = None

    def _shortcut_can_toggle(self, event):
        # Shortcuts only act while working with the image list or preview, not while
        # typing in a dialog or clicking toolbar controls.
        return event.widget in (self.image_tree, self.canvas)

    def _space_shortcut(self, event):
        if not self._shortcut_can_toggle(event):
            return
        self.toggle_current_image()
        return "break"

    def _enter_shortcut(self, event):
        if not self._shortcut_can_toggle(event):
            return
        self.toggle_current_image()
        return "break"

    def toggle_current_image(self):
        # Toggle semantics: first Space/Enter selects, the next deselects.
        selection = self.image_tree.selection()
        if selection:
            try:
                idx = int(selection[0])
                if 0 <= idx < len(self.image_paths):
                    self.current_image = self.image_paths[idx]
            except (ValueError, IndexError):
                pass
        if self.current_image is not None:
            self.toggle_path(self.current_image)

    def select_all(self):
        self.selected.update(self.image_paths)
        self._selected_here_count = sum(1 for p in self.image_paths if p in self.selected)
        for idx, path in enumerate(self.image_paths):
            self.image_tree.item(str(idx), image=self._checkbox_images[path in self.selected])
        self.update_counts()

    def deselect_current(self):
        """Deselect only the image currently shown in the right preview."""
        path = self.current_image
        if path is None:
            self.status.config(text="Chưa có ảnh đang xem để bỏ chọn.")
            return
        if path not in self.selected:
            self.status.config(text=f"Ảnh chưa được chọn: {path.name}")
            return
        self.toggle_path(path)
        self.status.config(text=f"Đã bỏ chọn ảnh đang xem: {path.name}")

    def deselect_all(self):
        """Clear selections across every scanned folder, not only the current folder."""
        self.selected.clear()
        self._selected_here_count = 0
        for idx in range(len(self.image_paths)):
            self.image_tree.item(str(idx), image=self._checkbox_images[False])
        self.update_counts()
        self.status.config(text="Đã bỏ chọn tất cả ảnh trong toàn bộ danh sách.")

    def update_counts(self):
        self.count_label.config(text=f"{len(self.image_paths)} ảnh | {self._selected_here_count} chọn")
        self.selected_label.config(text=f"Tổng ảnh đã chọn: {len(self.selected)}")

    def show_relative_image(self, delta: int):
        if not self.image_paths or self.current_image not in self.image_paths:
            return
        idx = self.image_paths.index(self.current_image)
        idx = (idx + delta) % len(self.image_paths)
        iid = str(idx)
        self.image_tree.selection_set(iid)
        self.image_tree.focus(iid)
        self.image_tree.see(iid)
        self.display_image(self.image_paths[idx])

    def _load_saved_ffmpeg_path(self):
        config = Path(__file__).with_name("ffmpeg_path.txt")
        try:
            candidate = Path(config.read_text(encoding="utf-8").strip().strip('"'))
            if candidate.is_file() and candidate.name.lower() == "ffmpeg.exe":
                return candidate
        except (OSError, ValueError):
            pass
        return None

    def _save_ffmpeg_path(self, path: Path):
        self.ffmpeg_path = path
        try:
            Path(__file__).with_name("ffmpeg_path.txt").write_text(str(path), encoding="utf-8")
        except OSError:
            # The current session still works even if the script directory is read-only.
            pass

    def _find_ffmpeg(self, extra_dirs=None):
        """Return (executable path, discovery description); PATH is preferred."""
        from_path = shutil.which("ffmpeg")
        if from_path:
            return Path(from_path), "Tìm thấy FFmpeg trong PATH."
        if self.ffmpeg_path and self.ffmpeg_path.is_file():
            return self.ffmpeg_path, "Tìm thấy FFmpeg theo đường dẫn đã lưu (chưa chắc đã nằm trong PATH)."

        candidates = []
        bases = [Path(__file__).resolve().parent, Path.cwd()]
        if self.root_dir:
            bases.append(self.root_dir)
        for extra in (extra_dirs or []):
            try:
                if extra and extra.is_dir():
                    bases.append(extra)
            except OSError:
                pass
        for base in bases:
            candidates.extend([base / "ffmpeg.exe", base / "bin" / "ffmpeg.exe", base / "ffmpeg" / "bin" / "ffmpeg.exe"])
        candidates.extend([
            Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
            Path(r"C:\Program Files\FFmpeg\bin\ffmpeg.exe"),
            Path(r"C:\Program Files (x86)\FFmpeg\bin\ffmpeg.exe"),
        ])
        seen = set()
        for candidate in candidates:
            try:
                normalized = str(candidate.resolve()).casefold()
                if normalized in seen:
                    continue
                seen.add(normalized)
                if candidate.is_file() and candidate.name.lower() == "ffmpeg.exe":
                    return candidate.resolve(), "Tìm thấy ffmpeg.exe nhưng chưa thêm vào PATH. Tool vẫn có thể dùng đường dẫn trực tiếp."
            except OSError:
                continue
        return None, "Không tìm thấy FFmpeg trong PATH hoặc các vị trí thường dùng. Có thể FFmpeg đã tải về nhưng chưa đặt đúng vị trí."

    @staticmethod
    def _test_ffmpeg(executable: Path):
        try:
            completed = subprocess.run(
                [str(executable), "-version"], capture_output=True, text=True,
                timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            if completed.returncode == 0 and "ffmpeg version" in (completed.stdout + completed.stderr).lower():
                return True, (completed.stdout or completed.stderr).splitlines()[0].strip()
            return False, (completed.stderr or completed.stdout or "FFmpeg không trả về thông tin phiên bản.").strip()[:600]
        except Exception as exc:
            return False, str(exc)

    def open_video_to_img_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Video → IMG | Trích xuất frame bằng FFmpeg")
        win.geometry("780x455")
        win.minsize(700, 420)
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="VIDEO → IMG", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text="Mỗi video sẽ tạo một thư mục riêng theo tên video. Mặc định 1 ảnh/giây; ảnh được đánh số frame_0001.jpg, frame_0002.jpg...",
            wraplength=720, justify="left"
        ).pack(anchor="w", pady=(5, 12))

        folder_var = tk.StringVar(value=str(self.root_dir or Path.cwd()))
        folder_row = ttk.Frame(frame)
        folder_row.pack(fill=tk.X, pady=3)
        ttk.Label(folder_row, text="Thư mục chứa video:", width=22).pack(side=tk.LEFT)
        folder_entry = ttk.Entry(folder_row, textvariable=folder_var)
        folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        def browse_video_folder():
            chosen = filedialog.askdirectory(title="Chọn thư mục có các file video", initialdir=folder_var.get() or str(Path.cwd()), parent=win)
            if chosen:
                folder_var.set(chosen)

        ttk.Button(folder_row, text="Duyệt...", command=browse_video_folder).pack(side=tk.LEFT)

        fps_var = tk.StringVar(value="1")
        fps_row = ttk.Frame(frame)
        fps_row.pack(fill=tk.X, pady=7)
        ttk.Label(fps_row, text="Ảnh mỗi giây (FPS):", width=22).pack(side=tk.LEFT)
        fps_entry = ttk.Entry(fps_row, textvariable=fps_var, width=12)
        fps_entry.pack(side=tk.LEFT, padx=6)
        ttk.Label(fps_row, text="Mặc định 1 = 1 ảnh/giây; 2 = 2 ảnh/giây; 0.5 = 1 ảnh mỗi 2 giây.").pack(side=tk.LEFT, fill=tk.X, expand=True)

        ffmpeg_frame = ttk.LabelFrame(frame, text="Kiểm tra FFmpeg", padding=10)
        ffmpeg_frame.pack(fill=tk.X, pady=(8, 8))
        ffmpeg_status = ttk.Label(ffmpeg_frame, text="Đang kiểm tra...", wraplength=680, justify="left")
        ffmpeg_status.pack(anchor="w", fill=tk.X, pady=(0, 6))
        ffmpeg_path_label = ttk.Label(ffmpeg_frame, text="", foreground="#4b5563", wraplength=680, justify="left")
        ffmpeg_path_label.pack(anchor="w", fill=tk.X)
        ffmpeg_buttons = ttk.Frame(ffmpeg_frame)
        ffmpeg_buttons.pack(fill=tk.X, pady=(7, 0))

        progress = ttk.Progressbar(frame, mode="indeterminate")
        progress.pack(fill=tk.X, pady=(4, 6))
        run_status = ttk.Label(frame, text="Sẵn sàng.", wraplength=720)
        run_status.pack(anchor="w", fill=tk.X)
        bottom = ttk.Frame(frame)
        bottom.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        run_button = ttk.Button(bottom, text="Bắt đầu tách ảnh", style="Tool.TButton")
        run_button.pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Đóng", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

        def update_ffmpeg_status():
            candidate_video_dir = Path(folder_var.get().strip().strip('"')) if folder_var.get().strip() else None
            executable, explanation = self._find_ffmpeg(extra_dirs=[candidate_video_dir] if candidate_video_dir else [])
            if executable:
                ok, version = self._test_ffmpeg(executable)
                if ok:
                    ffmpeg_status.config(text="✓ " + explanation, foreground="#176b35")
                    ffmpeg_path_label.config(text=f"Đường dẫn đang dùng: {executable}\n{version}")
                    run_button.state(["!disabled"])
                    return executable
                ffmpeg_status.config(text="⚠ Đã tìm thấy file nhưng chạy thử thất bại.", foreground="#a15c00")
                ffmpeg_path_label.config(text=f"{executable}\n{version}")
            else:
                ffmpeg_status.config(text="✕ " + explanation, foreground="#b42318")
                ffmpeg_path_label.config(text="Hãy chọn đúng file ffmpeg.exe hoặc thêm thư mục bin của FFmpeg vào PATH.")
            run_button.state(["disabled"])
            return None

        def browse_ffmpeg():
            chosen = filedialog.askopenfilename(
                title="Chọn ffmpeg.exe", filetypes=[("FFmpeg executable", "ffmpeg.exe"), ("Executable", "*.exe"), ("All files", "*.*")], parent=win
            )
            if not chosen:
                return
            candidate = Path(chosen)
            ok, details = self._test_ffmpeg(candidate)
            if not ok:
                messagebox.showerror("FFmpeg không hợp lệ", f"Không chạy được file này:\n{candidate}\n\n{details}", parent=win)
                return
            self._save_ffmpeg_path(candidate)
            update_ffmpeg_status()

        ttk.Button(ffmpeg_buttons, text="Kiểm tra lại", command=update_ffmpeg_status).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(ffmpeg_buttons, text="Chọn ffmpeg.exe...", command=browse_ffmpeg).pack(side=tk.LEFT)
        update_ffmpeg_status()

        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".webm", ".mpeg", ".mpg", ".3gp", ".mts", ".m2ts"}

        def start_extraction():
            executable = update_ffmpeg_status()
            if not executable:
                messagebox.showwarning("Chưa có FFmpeg", "Hãy cài FFmpeg, thêm vào PATH hoặc chọn đúng ffmpeg.exe trước.", parent=win)
                return
            folder_text = folder_var.get().strip().strip('"')
            video_folder = Path(folder_text) if folder_text else None
            if not video_folder or not video_folder.is_dir():
                messagebox.showerror("Thư mục không hợp lệ", "Hãy chọn thư mục đang chứa các file video.", parent=win)
                return
            try:
                fps = float(fps_var.get().strip().replace(",", "."))
                if not math.isfinite(fps) or fps <= 0 or fps > 240:
                    raise ValueError
            except ValueError:
                messagebox.showerror("FPS không hợp lệ", "Nhập số lớn hơn 0 và không quá 240, ví dụ 1, 2 hoặc 0.5.", parent=win)
                return

            videos = sorted([p for p in video_folder.iterdir() if p.is_file() and p.suffix.lower() in video_exts], key=lambda p: p.name.casefold())
            if not videos:
                messagebox.showinfo("Không tìm thấy video", "Không tìm thấy video trong thư mục đã chọn. Tool quét thư mục này, không quét thư mục con.", parent=win)
                return
            def already_done_at_fps(video: Path, requested_fps: float) -> bool:
                marker = video_folder / video.stem / "_DONE.txt"
                if not marker.is_file():
                    return False
                try:
                    marker_text = marker.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return True
                match = re.search(r"^FPS:\s*([0-9]+(?:\.[0-9]+)?)\s*$", marker_text, flags=re.IGNORECASE | re.MULTILINE)
                if match:
                    try:
                        return math.isclose(float(match.group(1)), requested_fps, rel_tol=1e-9, abs_tol=1e-9)
                    except ValueError:
                        return False
                # The older 1.bat had no FPS in its marker but always used fps=1.
                return math.isclose(requested_fps, 1.0, rel_tol=1e-9, abs_tol=1e-9)

            skipped_done = [v for v in videos if already_done_at_fps(v, fps)]
            queue_videos = [v for v in videos if v not in skipped_done]
            if not queue_videos:
                messagebox.showinfo("Đã hoàn tất trước đó", f"Tất cả {len(videos)} video đã được xử lý ở {fps:g} FPS và sẽ được bỏ qua.", parent=win)
                return
            if not messagebox.askyesno(
                "Xác nhận trích xuất",
                f"Tìm thấy {len(videos)} video.\nĐã hoàn tất nên bỏ qua: {len(skipped_done)}\nSẽ xử lý: {len(queue_videos)}\n\nFPS: {fps:g} ảnh/giây\nThư mục đầu ra: mỗi video tạo một thư mục cùng tên.\n\nTiếp tục?",
                parent=win
            ):
                return

            run_button.state(["disabled"])
            progress.start(10)
            run_status.config(text=f"Đang xử lý 0/{len(queue_videos)} video...")

            def extraction_worker():
                copied_done = 0
                skipped_existing = len(skipped_done)
                failures = []
                for i, video in enumerate(queue_videos, 1):
                    self._video_status_queue.put(("status", f"Đang xử lý {i}/{len(queue_videos)}: {video.name}"))
                    output_dir = video_folder / video.stem
                    temp_dir = None
                    try:
                        temp_dir = Path(tempfile.mkdtemp(prefix=f".{video.stem}_ffmpeg_tmp_", dir=str(video_folder)))
                        output_pattern = str(temp_dir / "frame_%04d.jpg")
                        command = [
                            str(executable), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
                            "-vf", f"fps={fps:g}", "-q:v", "2", output_pattern
                        ]
                        proc = subprocess.run(command, capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        if proc.returncode != 0:
                            raise RuntimeError((proc.stderr or proc.stdout or f"FFmpeg exited with code {proc.returncode}").strip()[-1800:])
                        new_frames = sorted(temp_dir.glob("frame_*.jpg"), key=lambda p: p.name.casefold())
                        if not new_frames:
                            raise RuntimeError("FFmpeg chạy xong nhưng không tạo được ảnh nào.")
                        output_dir.mkdir(parents=True, exist_ok=True)
                        # A folder without _DONE is an incomplete extraction. Replace only generated frame_####.jpg files after the temporary run succeeds.
                        for old in output_dir.iterdir():
                            if old.is_file() and re.fullmatch(r"frame_\d{4,}\.jpg", old.name, flags=re.IGNORECASE):
                                old.unlink()
                        for frame in new_frames:
                            shutil.move(str(frame), str(output_dir / frame.name))
                        marker_text = f"Completed: {video.name}\nFPS: {fps:g}\nFrames: {len(new_frames)}\n"
                        (output_dir / "_DONE.txt").write_text(marker_text, encoding="utf-8")
                        copied_done += 1
                    except Exception as exc:
                        failures.append(f"{video.name}: {exc}")
                    finally:
                        if temp_dir is not None:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                self._video_status_queue.put(("done", (copied_done, skipped_existing, failures, len(videos), fps, video_folder)))

            self._video_status_queue = queue.Queue()
            threading.Thread(target=extraction_worker, daemon=True, name="video-to-img").start()
            win.after(100, lambda: poll_extraction_status(win, progress, run_status, run_button))

        def poll_extraction_status(window, bar, status_label, button):
            try:
                while True:
                    kind, value = self._video_status_queue.get_nowait()
                    if kind == "status":
                        status_label.config(text=value)
                    elif kind == "done":
                        completed, skipped, errors, total, used_fps, out_folder = value
                        bar.stop()
                        button.state(["!disabled"])
                        self.status.config(text=f"Video → IMG hoàn tất: {completed} đã xử lý, {skipped} bỏ qua, {len(errors)} lỗi.")
                        status_label.config(text=f"Hoàn tất: {completed} xử lý thành công, {skipped} bỏ qua, {len(errors)} lỗi.")
                        details = f"Xử lý thành công: {completed} video\nĐã bỏ qua: {skipped} video\nLỗi: {len(errors)} video\nFPS: {used_fps:g}\nThư mục: {out_folder}"
                        if errors:
                            details += "\n\nChi tiết lỗi:\n" + "\n".join(errors[:8])
                        messagebox.showinfo("Kết quả Video → IMG", details, parent=window)
                        if not errors and self.root_dir:
                            # Refresh image folders if the converted videos are under the selected root.
                            try:
                                if out_folder == self.root_dir or self.root_dir in out_folder.parents:
                                    self.refresh_root()
                            except Exception:
                                pass
                        return
            except queue.Empty:
                pass
            if window.winfo_exists():
                window.after(100, lambda: poll_extraction_status(window, bar, status_label, button))

        run_button.config(command=start_extraction)

    def copy_selected(self):
        if not self.selected:
            messagebox.showinfo("Chưa chọn ảnh", "Hãy tick ít nhất một ảnh ở danh sách bên trái.")
            return
        groups: dict[Path, list[Path]] = {}
        for path in sorted(self.selected, key=lambda p: (str(p.parent).lower(), p.name.lower())):
            groups.setdefault(path.parent, []).append(path)
        copied = skipped = 0
        errors: list[str] = []
        for source_dir, files in groups.items():
            dest_dir = source_dir / "Đã lọc hình"
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                errors.append(f"{dest_dir}: {exc}")
                continue
            for src in files:
                dest = dest_dir / src.name
                if dest.exists():
                    skipped += 1
                    continue
                try:
                    shutil.copy2(src, dest)
                    copied += 1
                except Exception as exc:
                    errors.append(f"{src.name}: {exc}")
        summary = f"Đã copy: {copied} ảnh\nBỏ qua do đã tồn tại: {skipped} ảnh\nThư mục đích: mỗi thư mục video/Đã lọc hình"
        if errors:
            summary += "\n\nLỗi:\n" + "\n".join(errors[:10])
        messagebox.showinfo("Kết quả copy", summary)
        self.status.config(text=f"Copy xong: {copied}, bỏ qua: {skipped}, lỗi: {len(errors)}")

    # ------------------------------------------------------------------
    # Copy selected images cropped to the current view (zoom level + position)
    # ------------------------------------------------------------------
    def _view_crop_box(self, size, view):
        """Source-pixel box (l, t, r, b) that the viewer would show for an image of `size`.

        Mirrors what happens when you step to another image: zoom level stays the same and the
        view centre keeps its relative position. In "Vừa khung" mode the whole image is shown.
        """
        ow, oh = size
        if view["fit"]:
            return (0, 0, ow, oh)
        s = view["scale"]
        cx = self._clamp_axis(view["fx"] * ow, ow, view["cw"], s)
        cy = self._clamp_axis(view["fy"] * oh, oh, view["ch"], s)
        half_w, half_h = view["cw"] / (2 * s), view["ch"] / (2 * s)
        left = max(0, min(ow - 1, round(cx - half_w)))
        top = max(0, min(oh - 1, round(cy - half_h)))
        right = max(left + 1, min(ow, round(cx + half_w)))
        bottom = max(top + 1, min(oh, round(cy + half_h)))
        return (left, top, right, bottom)

    @staticmethod
    def _screen_scale(size, view):
        """Scale at which `size`-sized image is shown on screen for this view."""
        if view["fit"]:
            return min(view["cw"] / max(size[0], 1), view["ch"] / max(size[1], 1), 1.0)
        return view["scale"]

    def _crop_one(self, src: Path, dest: Path, view, mode: str, preloaded=None):
        if preloaded is not None:
            image = preloaded
            icc = image.info.get("icc_profile")
        else:
            with Image.open(src) as opened:
                icc = opened.info.get("icc_profile")
                image = ImageOps.exif_transpose(opened).convert("RGB")
        box = self._view_crop_box(image.size, view)
        part = image.crop(box)
        if mode == "screen":
            scale = self._screen_scale(image.size, view)
            if abs(scale - 1.0) > 1e-6:
                resample = Image.Resampling.LANCZOS if scale < 1 else Image.Resampling.BICUBIC
                part = part.resize((max(1, round(part.width * scale)), max(1, round(part.height * scale))), resample)
        options = {}
        if icc:
            options["icc_profile"] = icc
        ext = dest.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            options.update(quality=95, subsampling=0)
        elif ext == ".webp":
            options.update(quality=95)
        part.save(dest, **options)
        return box, part.size

    def _run_crop_job(self, files, view, mode, current_path, current_image, progress=None):
        """Crop every file in `files`. Returns (saved, errors). Safe to run in a worker thread."""
        saved = 0
        errors: list[str] = []
        total = len(files)
        for index, src in enumerate(files, 1):
            if progress:
                progress(index - 1, total, src.name)
            try:
                dest_dir = src.parent / "Đã lọc hình"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / f"{src.stem}_crop{src.suffix}"
                preloaded = current_image if (src == current_path and current_image is not None) else None
                self._crop_one(src, dest, view, mode, preloaded)
                saved += 1
            except Exception as exc:
                errors.append(f"{src.name}: {exc}")
        if progress:
            progress(total, total, "")
        return saved, errors

    def copy_selected_cropped(self):
        if not self.selected:
            messagebox.showinfo("Chưa chọn ảnh", "Hãy tick ít nhất một ảnh ở danh sách bên trái.")
            return
        if self.original_image is None or self.current_image is None:
            messagebox.showinfo("Chưa mở ảnh", "Hãy mở một ảnh và chỉnh zoom/vị trí khung xem trước khi copy.")
            return
        self._finish_zoom_animation()
        self._clamp_view()
        ow, oh = self.original_image.size
        cw, ch = self._viewport()
        view = {"fit": self.fit_mode, "scale": self.cur_scale, "cw": cw, "ch": ch,
                "fx": self.view_cx / ow, "fy": self.view_cy / oh}
        current_path, current_image = self.current_image, self.original_image
        files = sorted(self.selected, key=lambda p: (str(p.parent).lower(), p.name.lower()))
        left, top, right, bottom = self._view_crop_box((ow, oh), view)

        dialog = tk.Toplevel(self.root)
        dialog.title("Copy ảnh đã chọn theo khung zoom")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text=f"Cắt {len(files)} ảnh đã chọn theo khung đang xem.",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        if view["fit"]:
            info = "Đang ở chế độ “Vừa khung” → mỗi ảnh được copy nguyên khung hình."
        else:
            info = (f"Zoom {round(view['scale'] * 100)}%  |  vùng cắt trên ảnh đang xem: "
                    f"{right - left} × {bottom - top} px")
        ttk.Label(body, text=info, foreground="#1f4e79", wraplength=430).pack(anchor="w", pady=(6, 8))
        scale = self._screen_scale((ow, oh), view)
        native_w, native_h = right - left, bottom - top
        screen_w, screen_h = max(1, round(native_w * scale)), max(1, round(native_h * scale))
        if abs(scale - 1.0) < 1e-6:
            native_hint = (f"→ Ảnh ra {native_w} × {native_h} px. Ở mức 100% hai chế độ cho kết quả "
                           "giống hệt nhau.")
            screen_hint = "→ Giống chế độ ‘giữ độ phân giải gốc’ vì đang xem đúng 100%."
        else:
            if scale > 1:
                native_tail = ("✔ Sắc nét nhất, giữ đủ chi tiết; file (KB) nhẹ vì ít pixel.\n"
                               "✘ Ảnh ra nhỏ hơn khung đang xem; zoom càng lớn ảnh ra càng nhỏ.")
            else:
                native_tail = ("✔ Sắc nét nhất, giữ trọn chi tiết của ảnh gốc.\n"
                               "✘ Ảnh ra lớn hơn khung đang xem nên file (KB) nặng hơn.")
            native_hint = (f"→ Ảnh ra {native_w} × {native_h} px, lấy thẳng pixel gốc, không phóng/thu.\n"
                           + native_tail)
            if scale > 1:
                screen_hint = (f"→ Ảnh ra {screen_w} × {screen_h} px (≈ cỡ khung đang xem), nhiều hơn khoảng "
                               f"{scale * scale:.1f}× số pixel so với chế độ gốc.\n"
                               "✔ Ảnh to sẵn, đúng như thấy trên màn hình, dùng ngay được.\n"
                               "✘ Chỉ phóng to bằng nội suy: không thêm chi tiết, hơi mềm, file (KB) nặng hơn.")
            else:
                screen_hint = (f"→ Ảnh ra {screen_w} × {screen_h} px, thu nhỏ còn khoảng {scale * scale:.0%} "
                               "số pixel so với chế độ gốc.\n"
                               "✔ File nhẹ hơn, vừa với khung xem.\n"
                               "✘ Mất bớt chi tiết, không thể phóng to lại cho nét.")
        mode_var = tk.StringVar(value="native")
        hint_font = ("Segoe UI", 9)
        ttk.Radiobutton(body, text="Giữ độ phân giải gốc (khuyên dùng)", value="native",
                        variable=mode_var).pack(anchor="w")
        ttk.Label(body, text=native_hint, wraplength=410, justify=tk.LEFT, foreground="#4b5563",
                  font=hint_font).pack(anchor="w", padx=(24, 0), pady=(0, 6))
        ttk.Radiobutton(body, text="Đúng kích thước như đang hiển thị trên màn hình", value="screen",
                        variable=mode_var).pack(anchor="w")
        ttk.Label(body, text=screen_hint, wraplength=410, justify=tk.LEFT, foreground="#4b5563",
                  font=hint_font).pack(anchor="w", padx=(24, 0), pady=(0, 6))
        ttk.Label(body, wraplength=430, justify=tk.LEFT, foreground="#4b5563", font=hint_font,
                  text="Màu sắc: cả hai chế độ giữ nguyên màu (kèm hồ sơ màu ICC nếu có) nên không khác nhau. "
                       "Dung lượng (KB) chủ yếu phụ thuộc số pixel của ảnh ra; JPEG lưu chất lượng 95.\n"
                       "Lưu vào thư mục ‘Đã lọc hình’ của từng thư mục ảnh, tên <tên ảnh>_crop. "
                       "File _crop cũ cùng tên sẽ bị ghi đè. Ảnh gốc không bị thay đổi."
                  ).pack(anchor="w", pady=(2, 8))
        progress_label = ttk.Label(body, text="")
        progress_label.pack(anchor="w")
        bar = ttk.Progressbar(body, maximum=len(files), mode="determinate", length=430)
        bar.pack(fill=tk.X, pady=(2, 10))
        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X)
        close_button = ttk.Button(buttons, text="Đóng", command=dialog.destroy)
        close_button.pack(side=tk.RIGHT)
        start_button = ttk.Button(buttons, text="Bắt đầu cắt & copy")
        start_button.pack(side=tk.RIGHT, padx=(0, 6))

        events: queue.Queue = queue.Queue()
        running = {"value": False}

        def poll():
            try:
                while True:
                    kind, *payload = events.get_nowait()
                    if kind == "progress":
                        done, total, name = payload
                        bar["value"] = done
                        progress_label.config(text=f"Đang xử lý {done + 1}/{total}: {name}" if name else "")
                    else:
                        saved, errors = payload
                        running["value"] = False
                        close_button.state(["!disabled"])
                        progress_label.config(text=f"Xong: {saved} ảnh")
                        summary = f"Đã lưu: {saved} ảnh\nThư mục đích: mỗi thư mục ảnh/Đã lọc hình (đuôi _crop)"
                        if errors:
                            summary += "\n\nLỗi:\n" + "\n".join(errors[:10])
                        self.status.config(text=f"Copy theo khung zoom xong: {saved} ảnh, lỗi: {len(errors)}")
                        messagebox.showinfo("Kết quả copy", summary, parent=dialog)
                        dialog.destroy()
                        return
            except queue.Empty:
                pass
            if dialog.winfo_exists():
                dialog.after(60, poll)

        def start():
            running["value"] = True
            start_button.state(["disabled"])
            close_button.state(["disabled"])
            mode = mode_var.get()

            def worker():
                saved, errors = self._run_crop_job(
                    files, view, mode, current_path, current_image,
                    progress=lambda done, total, name: events.put(("progress", done, total, name)))
                events.put(("done", saved, errors))

            threading.Thread(target=worker, name="crop-copy", daemon=True).start()
            poll()

        start_button.config(command=start)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None if running["value"] else dialog.destroy())
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_reqheight()) // 3
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.grab_set()
        start_button.focus_set()

    def clear_viewer(self):
        self._render_token += 1
        self._cancel_zoom_animation()
        self._cancel_hq()
        self.original_image = None
        self._pyramid = []
        self.current_image = None
        self.tk_image = None
        self._canvas_image_id = None
        self._frame_size = (0, 0)
        self._label_text = ""
        self.canvas.delete("all")
        self.hbar.set(0.0, 1.0)
        self.vbar.set(0.0, 1.0)
        self.current_label.config(text="Chọn ảnh để xem")


def main():
    """Start the app with visible diagnostics if Windows cannot create the UI."""
    root = None
    log_path = Path(__file__).with_name("viewimgpro_error.log")
    try:
        root = tk.Tk()
        root.report_callback_exception = lambda exc_type, exc_value, exc_tb: _report_error(
            log_path, exc_type, exc_value, exc_tb, root
        )
        app = VideoImageFilterApp(root)
        root.update_idletasks()
        # Make sure the window is visible and not hidden behind the command prompt.
        root.deiconify()
        root.lift()
        root.after(250, lambda: _bring_window_forward(root))
        root.mainloop()
    except Exception:
        details = traceback.format_exc()
        try:
            log_path.write_text(details, encoding="utf-8")
        except Exception:
            pass
        try:
            if root is not None and root.winfo_exists():
                messagebox.showerror(
                    "Loi khoi dong ViewImgPro",
                    f"Khong the mo giao dien. Chi tiet da duoc luu vao:\n{log_path}\n\n{details[-2500:]}"
                )
            else:
                # Try a standalone Tk message box even if app initialization failed.
                temp = tk.Tk()
                temp.withdraw()
                messagebox.showerror(
                    "Loi khoi dong ViewImgPro",
                    f"Khong the mo giao dien. Chi tiet da duoc luu vao:\n{log_path}\n\n{details[-2500:]}"
                )
                temp.destroy()
        except Exception:
            pass
        # Keep console output quiet; the error dialog and log file preserve diagnostics.


def _bring_window_forward(root):
    try:
        if root.winfo_exists():
            root.deiconify()
            root.lift()
            root.focus_force()
    except tk.TclError:
        pass


def _report_error(log_path, exc_type, exc_value, exc_tb, root):
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        log_path.write_text(details, encoding="utf-8")
    except Exception:
        pass
    try:
        messagebox.showerror(
            "ViewImgPro - Loi trong giao dien",
            f"Da xay ra loi trong giao dien. Log: {log_path}\n\n{details[-2500:]}",
            parent=root
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
