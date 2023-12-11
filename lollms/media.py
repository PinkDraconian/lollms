"""
Project: LoLLMs
Author: ParisNeo
Description: Media classes:
    - WebcamImageSender: is a captures images from the webcam and sends them to a SocketIO client.
    - MusicPlayer: is a MusicPlayer class that allows you to play music using pygame library.
License: Apache 2.0
"""
from lollms.utilities import PackageManager
from lollms.com import LoLLMsCom
if not PackageManager.check_package_installed("pygame"):
    PackageManager.install_package("pygame")
    import pygame
else:
    import pygame

import threading
if not PackageManager.check_package_installed("cv2"):
    PackageManager.install_package("opencv-python")
    import cv2
else:
    import cv2


if not PackageManager.check_package_installed("pyaudio"):
    PackageManager.install_package("pyaudio")
    PackageManager.install_package("wave")
    import pyaudio
    import wave
else:
    import pyaudio
    import wave


if not PackageManager.check_package_installed("scipy"):
    PackageManager.install_package("scipy")
    from scipy import signal
else:
    from scipy import signal

if not PackageManager.check_package_installed("matplotlib"):
    PackageManager.install_package("matplotlib")
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

from lollms.com import LoLLMsCom
import time
import json
import base64
import io
import numpy as np

class AudioRecorder:
    def __init__(self, socketio, filename, channels=1, sample_rate=44100, chunk_size=1024, silence_threshold=0.1, silence_duration=2, lollmsCom:LoLLMsCom=None):
        self.socketio = socketio
        self.filename = filename
        self.channels = channels
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio_format = pyaudio.paInt16
        self.audio_stream = None
        self.audio_frames = []
        self.is_recording = False
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.last_sound_time = time.time()
        self.lollmsCom = lollmsCom

    def start_recording(self):
        try:
            self.is_recording = True
            self.audio_stream = pyaudio.PyAudio().open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )

            self.lollmsCom.info("Recording started...")

            threading.Thread(target=self._record).start()
        except:
            self.lollmsCom.error("No audio input found!")
    def _record(self):
        while self.is_recording:
            data = self.audio_stream.read(self.chunk_size)
            self.audio_frames.append(data)

            # Check for silence
            rms = self._calculate_rms(data)
            if rms < self.silence_threshold:
                current_time = time.time()
                if current_time - self.last_sound_time >= self.silence_duration:
                    self.lollmsCom.info("Analyzing")
                    self.audio_stream.stop_stream()
                    self.audio_stream.close()

            else:
                self.last_sound_time = time.time()

            # Update spectrogram every second
            if len(self.audio_frames) % (self.sample_rate // self.chunk_size) == 0:
                self._update_spectrogram()

    def _calculate_rms(self, data):
        squared_sum = sum([sample ** 2 for sample in data])
        rms = (squared_sum / len(data)) ** 0.5
        return rms

    def _update_spectrogram(self):
        audio_data = np.frombuffer(b''.join(self.audio_frames), dtype=np.int16)
        frequencies, times, spectrogram = signal.spectrogram(audio_data, self.sample_rate)

        # Plot spectrogram
        plt.figure(figsize=(10, 4))
        plt.imshow(np.log(spectrogram), aspect='auto', origin='lower', cmap='inferno')
        plt.xlabel('Time')
        plt.ylabel('Frequency')
        plt.title('Spectrogram')
        plt.colorbar(format='%+2.0f dB')

        # Convert plot to base64 image
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')

        # Send base64 image using socketio
        self.socketio.emit('update_spectrogram', img_base64)

        plt.close()

    def stop_recording(self):
        self.is_recording = False
        self.audio_stream.stop_stream()
        self.audio_stream.close()

        audio = wave.open(str(self.filename), 'wb')
        audio.setnchannels(self.channels)
        audio.setsampwidth(pyaudio.PyAudio().get_sample_size(self.audio_format))
        audio.setframerate(self.sample_rate)
        audio.writeframes(b''.join(self.audio_frames))
        audio.close()

        self.lollmsCom.info(f"Recording saved to {self.filename}")


class WebcamImageSender:
    """
    Class for capturing images from the webcam and sending them to a SocketIO client.
    """

    def __init__(self, socketio, lollmsCom:LoLLMsCom=None):
        """
        Initializes the WebcamImageSender class.

        Args:
            socketio (socketio.Client): The SocketIO client object.
        """
        self.socketio = socketio
        self.last_image = None
        self.last_change_time = None
        self.capture_thread = None
        self.is_running = False
        self.lollmsCom = lollmsCom

    def start_capture(self):
        """
        Starts capturing images from the webcam in a separate thread.
        """
        self.is_running = True
        self.capture_thread = threading.Thread(target=self.capture_image)
        self.capture_thread.start()

    def stop_capture(self):
        """
        Stops capturing images from the webcam.
        """
        self.is_running = False
        self.capture_thread.join()

    def capture_image(self):
        """
        Captures images from the webcam, checks if the image content has changed, and sends the image to the client if it remains the same for 3 seconds.
        """
        try:
            cap = cv2.VideoCapture(0)

            while self.is_running:
                ret, frame = cap.read()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if self.last_image is None or self.image_difference(gray) > 2:
                    self.last_image = gray
                    self.last_change_time = time.time()

                _, buffer = cv2.imencode('.jpg', frame)
                image_base64 = base64.b64encode(buffer)
                self.socketio.emit("image", image_base64.decode('utf-8'))

            cap.release()
        except:
            self.lollmsCom.error("Couldn't start webcam")

    def image_difference(self, image):
        """
        Calculates the difference between two images using the absolute difference method.

        Args:
            image (numpy.ndarray): The current image.

        Returns:
            int: The sum of pixel intensities representing the difference between the current image and the last image.
        """
        if self.last_image is None:
            return 0

        diff = cv2.absdiff(image, self.last_image)
        diff_sum = diff.sum()

        return diff_sum

class MusicPlayer(threading.Thread):
    """
    MusicPlayer class for playing music using pygame library.

    Attributes:
    - file_path (str): The path of the music file to be played.
    - paused (bool): Flag to indicate if the music is paused.
    - stopped (bool): Flag to indicate if the music is stopped.
    """

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.paused = False
        self.stopped = False

    def run(self):
        """
        The main function that runs in a separate thread to play the music.
        """
        pygame.mixer.init()
        pygame.mixer.music.load(self.file_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy() and not self.stopped:
            if self.paused:
                pygame.mixer.music.pause()
            else:
                pygame.mixer.music.unpause()

    def pause(self):
        """
        Pauses the music.
        """
        self.paused = True

    def resume(self):
        """
        Resumes the paused music.
        """
        self.paused = False

    def stop(self):
        """
        Stops the music.
        """
        self.stopped = True
        pygame.mixer.music.stop()