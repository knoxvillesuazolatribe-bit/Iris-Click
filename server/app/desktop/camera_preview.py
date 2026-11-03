"""Floating camera preview with the "0 V 0" pointer drawn on the face.

Shows the mirrored frame the tracker sees, so the user can check framing and
lighting while navigating, and reports where the pupil midpoint sits on
screen so the gaze overlay can draw a line from the eyes to the cursor.
Draggable by its title; non-activating so it never takes keyboard focus.
"""

import tkinter as tk

from PIL import Image, ImageTk

from app.desktop.display import make_tool_window

PREVIEW_WIDTH = 320
BACKGROUND = "#0F1B2D"
TEXT = "#C9D6E8"
EYE = "#FFD23F"
NOSE = "#4DA3FF"
POINTER = "#FF6B6B"
MARGIN_PX = 16
# Keeps the default position above the Windows taskbar.
TASKBAR_PX = 56
FONT = ("Segoe UI", 10, "bold")


class CameraPreview:
    def __init__(self, root: tk.Misc, screen_w: int, screen_h: int):
        self.visible = True
        self._photo = None
        self._eye_point = None
        self._size = (PREVIEW_WIDTH, PREVIEW_WIDTH * 9 // 16)
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=NOSE)

        frame = tk.Frame(self.win, bg=BACKGROUND)
        frame.pack(padx=2, pady=2)
        title = tk.Label(frame, text="Camera   line: eyes → cursor   red dot: raw gaze",
                         font=FONT, bg=BACKGROUND, fg=TEXT, anchor="w", cursor="fleur",
                         padx=6, pady=3)
        title.pack(fill="x")
        title.bind("<ButtonPress-1>", self._start_drag)
        title.bind("<B1-Motion>", self._drag)
        self.canvas = tk.Canvas(frame, width=self._size[0], height=self._size[1], bg="black",
                                highlightthickness=0)
        self.canvas.pack()
        self._image_item = self.canvas.create_image(0, 0, anchor="nw")

        self.win.update_idletasks()
        x = screen_w - self.win.winfo_reqwidth() - MARGIN_PX
        y = screen_h - self.win.winfo_reqheight() - TASKBAR_PX
        self.win.geometry(f"+{x}+{y}")
        make_tool_window(self.win)

    def set_visible(self, visible: bool):
        self.visible = visible
        if visible:
            self.win.deiconify()
            self.win.attributes("-topmost", True)
        else:
            self.win.withdraw()
            self._eye_point = None

    def keep_on_top(self):
        if self.visible:
            self.win.attributes("-topmost", True)
            self.win.lift()

    def show(self, reading):
        """Draw a new ``GazeReading``; its ``preview`` is a mirrored RGB array."""
        if not self.visible:
            return
        frame = reading.preview
        if frame is not None:
            height, width = frame.shape[:2]
            if (width, height) != self._size:
                self._size = (width, height)
                self.canvas.configure(width=width, height=height)
            # Keep a reference: Tk drops images whose Python object is collected.
            self._photo = ImageTk.PhotoImage(Image.fromarray(frame))
            self.canvas.itemconfigure(self._image_item, image=self._photo)
        self.canvas.delete("face")
        eye_line = reading.eye_line if reading.face_found else None
        if not eye_line or "pointer" not in eye_line:
            self._eye_point = None
            self.canvas.create_text(self._size[0] / 2, self._size[1] - 14, text="No face",
                                    fill=POINTER, font=FONT, tags="face")
            return
        self._draw_face(eye_line)

    def _scaled(self, point) -> tuple[float, float]:
        return point[0] * self._size[0], point[1] * self._size[1]

    def _draw_face(self, eye_line: dict):
        """Both irises ("0 0"), the V down to the nose apex, and the pupil midpoint."""
        canvas = self.canvas
        left = self._scaled(eye_line["left_iris"])
        right = self._scaled(eye_line["right_iris"])
        tip = eye_line.get("nose_tip")
        if tip is not None:
            canvas.create_line(*left, *self._scaled(tip), *right, fill=NOSE, width=2,
                               tags="face")
        for x, y in (left, right):
            canvas.create_oval(x - 5, y - 5, x + 5, y + 5, outline=EYE, width=2, tags="face")
        x, y = self._eye_point = self._scaled(eye_line["pointer"])
        canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=POINTER, outline="", tags="face")

    def eye_point_on_screen(self) -> tuple[float, float] | None:
        """The pupil midpoint in physical screen pixels, or None without a face."""
        if not self.visible or self._eye_point is None:
            return None
        x, y = self._eye_point
        return self.canvas.winfo_rootx() + x, self.canvas.winfo_rooty() + y

    def _start_drag(self, event):
        self._drag_offset = (event.x_root - self.win.winfo_x(), event.y_root - self.win.winfo_y())

    def _drag(self, event):
        dx, dy = self._drag_offset
        self.win.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
