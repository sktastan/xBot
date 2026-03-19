# ---------------------------------------------------------------------
#   Text-to-Speech (TTS) engine wrapper using Piper.
# -------------------------------------------------------------------
import subprocess
import re
import os
from piper.voice import PiperVoice

# ---------------------------------------------------------------------
#   Text-to-Speech engine wrapper using Piper.
# -------------------------------------------------------------------
class TTS:
    def __init__(self):
        self.piper_voice = None
        # Default to joe as per previous user edit
        # self.model_path = os.path.abspath("piper-voices/en/en_US/hfc_male/medium/en_US-hfc_male-medium.onnx")
        self.model_path = os.path.abspath("piper-voices/en/en_US/joe/medium/en_US-joe-medium.onnx")
        self.config_path = self.model_path + ".json"
        self.enabled = True

    # ---------------------------------------------------------------------
    #   Loads the Piper model if not already loaded.
    # -------------------------------------------------------------------
    def _load_piper(self):
        if self.piper_voice is None:
            if os.path.exists(self.model_path):
                self.piper_voice = PiperVoice.load(self.model_path, config_path=self.config_path)
            else:
                print(f"[Error] Piper model not found at {self.model_path}.")
                return False
        return True

    # ---------------------------------------------------------------------
    #   Switches the current voice model.
    # -------------------------------------------------------------------
    def setVoice(self, voice_name: str):
        """
        Dynamically switch the Piper voice model by searching for the voice name in piper-voices/en/en_US.
        Example: setVoice("ryan")
        """
        base_dir = os.path.abspath("piper-voices/en/en_US")
        found = False
        
        # Search recursively for the .onnx file matching the voice name
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".onnx") and voice_name.lower() in file.lower():
                    self.model_path = os.path.join(root, file)
                    self.config_path = self.model_path + ".json"
                    self.piper_voice = None # Reset to trigger reload
                    print(f"[Info] Switched to voice: {voice_name} ({file})")
                    found = True
                    break
            if found: break
        
        if not found:
            print(f"[Warning] Voice '{voice_name}' not found. Keeping current voice.")

    # ---------------------------------------------------------------------
    #   Retrieves available voice names from the models directory.
    # -------------------------------------------------------------------
    def get_voices(self):
        """
        Returns a list of available voice names.
        """
        base_dir = os.path.abspath("piper-voices/en/en_US")
        voices = []
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".onnx"):
                    voices.append(file.replace(".onnx", ""))
        return voices   

    # ---------------------------------------------------------------------
    #   Gets the currently active voice name.
    # -------------------------------------------------------------------
    def get_current_voice(self):
        """
        Returns the current voice name.
        """
        return self.model_path.replace(".onnx", "") 


    # ---------------------------------------------------------------------
    #   Generates audio PCM chunks for the given text.
    # -------------------------------------------------------------------
    async def generate_audio_stream(self, text: str):
        """
        Async generator that yields raw PCM chunks from Piper.
        """
        if not self.enabled:
            return

        if self._load_piper():
            # PiperVoice.synthesize yields AudioChunk objects or raw bytes
            for item in self.piper_voice.synthesize(text):
                audio_data = None
                if hasattr(item, "audio_int16_bytes"):
                    audio_data = item.audio_int16_bytes
                elif hasattr(item, "audio"): # Legacy check
                    audio_data = item.audio
                elif hasattr(item, "audio_float_array"):
                    audio_data = item.audio_float_array
                elif isinstance(item, bytes):
                    audio_data = item
                    
                if audio_data is not None:
                    if isinstance(audio_data, bytes):
                        yield audio_data
                    elif hasattr(audio_data, "tobytes"):
                        yield audio_data.tobytes()

    # ---------------------------------------------------------------------
    #   Processes chunks, generates audio, and saves to file.
    # -------------------------------------------------------------------
    async def play_and_save_stream(self, chunks, output_path="response.wav"):
        """
        Processes LLM text chunks into sentences, generates TTS audio,
        saves to a WAV file, and yields text chunks to the caller.
        Audio playback is handled client-side via the /audio endpoint.
        """
        import wave
        sentence_buffer = ""

        # Ensure we use .wav for output
        if not output_path.endswith(".wav"):
            output_path = os.path.splitext(output_path)[0] + ".wav"

        with wave.open(output_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(22050)

            for chunk in chunks:
                yield chunk
                print(chunk, end="", flush=True)
                sentence_buffer += chunk

                # Check for sentence boundaries
                if re.search(r'[.!?](\s|$)', sentence_buffer):
                    sentences = re.split(r'(?<=[.!?])\s+', sentence_buffer)

                    if len(sentences) > 1:
                        to_process = sentences[:-1]
                        sentence_buffer = sentences[-1]

                        for s in to_process:
                            if s.strip():
                                async for audio_chunk in self.generate_audio_stream(s):
                                    wav_file.writeframes(audio_chunk)

            # Process any remaining text
            if sentence_buffer.strip():
                async for audio_chunk in self.generate_audio_stream(sentence_buffer):
                    wav_file.writeframes(audio_chunk)
