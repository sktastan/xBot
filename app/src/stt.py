# ---------------------------------------------------------------------
#   Speech-to-Text (STT) wrapper using Faster Whisper.
# -------------------------------------------------------------------
from faster_whisper import WhisperModel

# ---------------------------------------------------------------------
#   Speech-to-Text wrapper using Faster Whisper.
# -------------------------------------------------------------------
class STT:
    def __init__(self):
        model_size = "base"
        self.segments = None
        self.info = None

        try:
            # Attempt to run on GPU with FP16
            self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
        except Exception as e:
            print(f"STT: CUDA initialization failed ({e}). Falling back to CPU.")
            # Fallback to CPU with int8 quantization for better performance on processors
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            
        self.enabled = True

    # ---------------------------------------------------------------------
    #   Transcribes the audio file at the given path.
    # -------------------------------------------------------------------
    def transcribe(self, audio_path):
        self.segments, self.info = self.model.transcribe(audio_path, beam_size=1, vad_filter=True)
        return "".join(segment.text for segment in self.segments)
    
    
    # ---------------------------------------------------------------------
    #   Returns the raw segments from the last transcription.
    # -------------------------------------------------------------------
    def get_segments(self):
        return self.segments
    
    # ---------------------------------------------------------------------
    #   Returns metadata info from the last transcription.
    # -------------------------------------------------------------------
    def get_info(self):
        return self.info
