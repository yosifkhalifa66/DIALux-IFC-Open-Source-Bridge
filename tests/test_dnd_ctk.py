import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

if __name__ == "__main__":
    app = DnDCTk()
    app.geometry("400x300")
    label = ctk.CTkLabel(app, text="Drop test")
    label.pack(pady=20)
    print("DnDCTk initialized successfully!")
    app.destroy()
