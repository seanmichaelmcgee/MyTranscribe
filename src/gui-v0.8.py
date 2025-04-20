import sys
import time
import gi
import torch
import whisper
import numpy as np
import logging
from transcriber_v12 import RealTimeTranscriber
from pynput import keyboard

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

# Configure logging for the application
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def apply_css():
    css = b"""
    .start-button {
        background-color: #00FF00;
        color: black;
        font-weight: bold;
    }
    .stop-button {
        background-color: #FF0000;
        color: black;
        font-weight: bold;
    }
    .long-record-button {
        background-color: #0000FF;
        color: black;
        font-weight: bold;
    }
    .audio-indicator {
        background-color: #00AA00;
        border-radius: 2px;
    }
    """
    style_provider = Gtk.CssProvider()
    style_provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

class TranscriptionApp:
    def __init__(self):
        self.window = Gtk.Window()
        self.window.set_default_size(650, 200)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_title("Real-Time Transcription")
        # Always on top and slightly transparent
        self.window.set_keep_above(True)
        self.window.set_opacity(0.9)
        
        header_bar = Gtk.HeaderBar()
        header_bar.set_show_close_button(True)
        header_bar.set_title("Real-Time Transcription")
        self.window.set_titlebar(header_bar)
        
        self.transcribing = False
        self.recording_mode = None  # "normal" or "long"
        self.update_timeout_id = None
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = whisper.load_model("small", device=self.device)
        self.transcriber = RealTimeTranscriber(self.model)
        
        # Setup global hotkey tracking
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.q_pressed = False
        self.listener = keyboard.Listener(
            on_press=self.on_global_press,
            on_release=self.on_global_release)
        self.listener.start()
        
        self.init_ui()
        
        self.window.connect("destroy", self.on_destroy)
        self.window.connect("key-press-event", self.on_key_press)
        self.window.show_all()
    
    def init_ui(self):
        apply_css()
        
        # Main vertical container
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_vbox.set_border_width(10)
        
        # Create an overlay to position the audio indicator over the text view
        overlay = Gtk.Overlay()
        
        # Main text area with ScrolledWindow
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_cursor_visible(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_buffer = self.text_view.get_buffer()
        
        scroll.add(self.text_view)
        
        # Add the ScrolledWindow as the main widget in the overlay
        overlay.add(scroll)
        
        # Create a container for the audio indicator
        audio_indicator_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        audio_indicator_container.set_halign(Gtk.Align.END)  # Align to the right
        audio_indicator_container.set_valign(Gtk.Align.START)  # Align to the top
        audio_indicator_container.set_margin_top(5)
        audio_indicator_container.set_margin_end(5)
        
        # Simple audio indicator (a small box that will be shown/hidden)
        self.audio_indicator = Gtk.Box()
        self.audio_indicator.set_size_request(50, 4)  # Same size as previous level bar
        self.audio_indicator.get_style_context().add_class("audio-indicator")
        # Initially hidden
        self.audio_indicator.set_no_show_all(True)
        self.audio_indicator.hide()
        
        audio_indicator_container.pack_start(self.audio_indicator, False, False, 0)
        
        # Add the audio indicator container as an overlay widget
        overlay.add_overlay(audio_indicator_container)
        
        # Add the overlay to the main container
        main_vbox.pack_start(overlay, True, True, 0)
        
        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.start_button = Gtk.Button(label="Start")
        self.long_record_button = Gtk.Button(label="Long Record")
        self.stop_button = Gtk.Button(label="Stop")
        
        self.start_button.get_style_context().add_class("start-button")
        self.long_record_button.get_style_context().add_class("long-record-button")
        self.stop_button.get_style_context().add_class("stop-button")
        
        self.start_button.connect("clicked", self.start_transcription)
        self.long_record_button.connect("clicked", self.start_long_recording)
        self.stop_button.connect("clicked", self.stop_transcription)
        
        # Pack Start and Stop buttons on the left
        button_box.pack_start(self.start_button, True, True, 0)
        button_box.pack_start(self.stop_button, True, True, 0)
        # Pack the Long Record button to the right
        button_box.pack_end(self.long_record_button, True, True, 0)
        
        main_vbox.pack_start(button_box, False, False, 0)
        self.window.add(main_vbox)
        self.update_button_states()
    
    def on_destroy(self, widget):
        if self.listener.is_alive():
            self.listener.stop()
        Gtk.main_quit()
        
    def on_global_press(self, key):
        try:
            logging.debug(f"Key pressed: {key}")
            
            if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self.ctrl_pressed = True
                logging.debug("Ctrl pressed")
            elif key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                self.alt_pressed = True
                logging.debug("Alt pressed")
            elif hasattr(key, 'char') and key.char == 'q':
                self.q_pressed = True
                logging.debug("Q pressed (char attribute)")
            elif key == keyboard.KeyCode.from_char('q'):
                self.q_pressed = True
                logging.debug("Q pressed (KeyCode)")
                
            # Check for Ctrl+Alt+Q combination
            if self.ctrl_pressed and self.alt_pressed and self.q_pressed:
                logging.info("Global hotkey Ctrl+Alt+Q detected!")
                # Use GLib.idle_add to safely interact with GTK from another thread
                GLib.idle_add(self.toggle_transcription)
                # Reset to prevent multiple triggers
                self.q_pressed = False
        except (AttributeError, TypeError) as e:
            logging.debug(f"Exception in key press handler: {e}")
            
    def on_global_release(self, key):
        try:
            if key == keyboard.Key.ctrl or key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self.ctrl_pressed = False
            elif key == keyboard.Key.alt or key == keyboard.Key.alt_l or key == keyboard.Key.alt_r:
                self.alt_pressed = False
            elif hasattr(key, 'char') and key.char == 'q':
                self.q_pressed = False
            elif key == keyboard.KeyCode.from_char('q'):
                self.q_pressed = False
        except (AttributeError, TypeError):
            pass
    
    def toggle_transcription(self):
        if self.transcribing and self.recording_mode == "normal":
            logging.info("Stopping transcription via global hotkey")
            self.stop_transcription()
        elif not self.transcribing:
            logging.info("Starting transcription via global hotkey")
            self.start_transcription()
            # Ensure window is visible when started via global hotkey
            self.window.present()
        return False  # Important for GLib.idle_add to not repeat
    
    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_space:
            # Only toggle via space bar if in normal mode.
            if self.transcribing and self.recording_mode == "normal":
                self.stop_transcription()
            elif not self.transcribing:
                self.start_transcription()
    
    def start_transcription(self, widget=None):
        if self.transcribing:
            return
        self.recording_mode = "normal"
        self.transcribing = True
        self.text_buffer.set_text("")
        self.transcriber.transcriptions = []
        self.update_button_states()
        
        self.transcriber.start_recording(mode="normal")
        # Very frequent updates (30ms) for smoother audio level visualization
        self.update_timeout_id = GLib.timeout_add(30, self.update_transcription_callback)
    
    def start_long_recording(self, widget=None):
        if self.transcribing:
            return
        self.recording_mode = "long"
        self.transcribing = True
        self.text_buffer.set_text("")
        self.transcriber.transcriptions = []
        self.update_button_states()
        
        self.transcriber.start_recording(mode="long")
        # Very frequent updates for smoother animation
        self.update_timeout_id = GLib.timeout_add(30, self.update_transcription_callback)
    
    def stop_transcription(self, widget=None):
        if not self.transcribing:
            return
        self.transcribing = False
        self.recording_mode = None
        if self.update_timeout_id:
            GLib.source_remove(self.update_timeout_id)
            self.update_timeout_id = None
        
        self.transcriber.force_process_partial_frames()
        self.transcriber.stop_recording()
        self.update_button_states()
        
        final_text = "\n".join(self.transcriber.transcriptions)
        GLib.idle_add(self.text_buffer.set_text, final_text)
        self.copy_to_clipboard(final_text)
        
        # Hide the audio indicator
        self.audio_indicator.hide()
    
    def update_transcription_callback(self):
        if self.recording_mode == "long":
            # During long recording, display a placeholder message.
            self.text_buffer.set_text("Recording in long mode...")
        else:
            current_text = "\n".join(self.transcriber.transcriptions)
            self.text_buffer.set_text(current_text)
        
        # Update audio indicator visibility based on detection flag
        if self.transcriber.audio_detected:
            self.audio_indicator.show()
        else:
            self.audio_indicator.hide()
        
        return self.transcribing
    
    def copy_to_clipboard(self, text):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()
        print(f"[DEBUG] Copied to clipboard: {text[:60]}{'...' if len(text)>60 else ''}")
    
    def update_button_states(self):
        self.start_button.set_sensitive(not self.transcribing)
        self.long_record_button.set_sensitive(not self.transcribing)
        self.stop_button.set_sensitive(self.transcribing)

def main():
    logging.info("Starting MyTranscribe application")
    logging.info("Global hotkey Ctrl+Alt+Q is enabled")
    app = TranscriptionApp()
    Gtk.main()

if __name__ == "__main__":
    main()