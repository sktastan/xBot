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

        # Run on GPU with FP16
        self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
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
