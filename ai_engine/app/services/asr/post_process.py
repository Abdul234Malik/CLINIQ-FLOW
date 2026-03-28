import torchaudio
import soundfile as _sf
import numpy as _np

# Patch 1: list_audio_backends
if not hasattr(torchaudio, 'list_audio_backends'):
    torchaudio.list_audio_backends = lambda: ["soundfile"]

# Patch 2: set_audio_backend
if not hasattr(torchaudio, 'set_audio_backend'):
    torchaudio.set_audio_backend = lambda x: None

# Patch 3: AudioMetaData
if not hasattr(torchaudio, 'AudioMetaData'):
    from dataclasses import dataclass
    @dataclass
    class AudioMetaData:
        sample_rate: int = 0
        num_channels: int = 0
        num_frames: int = 0
        bits_per_sample: int = 0
        encoding: str = ""
    torchaudio.AudioMetaData = AudioMetaData

# Patch 4: torchaudio.info — uses soundfile to get audio metadata
def _patched_torchaudio_info(filepath, *args, **kwargs):
    info = _sf.info(filepath)
    return torchaudio.AudioMetaData(
        sample_rate=info.samplerate,
        num_channels=info.channels,
        num_frames=info.frames,
        bits_per_sample=16,
        encoding="PCM_S",
    )
torchaudio.info = _patched_torchaudio_info

# Patch 5: torchaudio.load — uses soundfile to load audio
import torch as _torch
def _patched_torchaudio_load(filepath, *args, **kwargs):
    kwargs.pop('backend', None)
    kwargs.pop('normalize', None)
    data, samplerate = _sf.read(filepath, dtype='float32', always_2d=True)
    tensor = _torch.from_numpy(data.T)
    return tensor, samplerate
torchaudio.load = _patched_torchaudio_load

# Now safe to import torch and pyannote
import torch
import lightning_fabric.utilities.cloud_io as _lf_io
import pytorch_lightning.core.saving as _pl_saving

def _safe_lf_load(path, map_location=None, **kwargs):
    kwargs.pop('weights_only', None)
    with open(path, 'rb') as f:
        return torch.load(f, map_location=map_location, weights_only=False)

_lf_io._load = _safe_lf_load
_pl_saving.pl_load = _safe_lf_load

_original_torch_load = torch.load
def _patched_torch_load(f, *args, **kwargs):
    kwargs['weights_only'] = False
    return _original_torch_load(f, *args, **kwargs)
torch.load = _patched_torch_load

from pyannote.audio import Pipeline as DiarizationPipeline
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request

from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
from transformers import WhisperForConditionalGeneration, WhisperProcessor
from huggingface_hub import snapshot_download


import torch
import librosa
import numpy as np
import soundfile as sf
import tempfile
import os
import logging
import time
import uuid
from contextlib import asynccontextmanager
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()



# Configure logging to show timestamp, level (INFO/ERROR), and message
# This prints to stdout which Railway/Render captures as server logs
logging.basicConfig(
    level  = logging.INFO,                         
    format = "%(asctime)s | %(levelname)s | %(message)s"  
)
logger = logging.getLogger(__name__)

API_KEY = os.environ.get("openai_key", "openai_key")
print(f"DEBUG: API_KEY loaded as = '{API_KEY}'") 

MODEL_ID = "openai/whisper-small"
HF_TOKEN = os.environ.get("HF_TOKEN")
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:8000").split(",")
CACHE_DIR = os.environ.get("CACHE_DIR", "./model_cache")

SAMPLE_RATE = 16000
MAX_FILE_MB = 50
MIN_DURATION_S = 0

ALLOWED_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/webm",
    "audio/ogg",
    "application/octet-stream"
}

session_store = defaultdict(list)

# Rate limiter 

# get_remote_address extracts the caller's IP from each request
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


#  Model manager
# Holds both the Whisper model and pyannote diarizer in memory
# Defined as a class so we can access them from any endpoint function
# Both are loaded once at startup and reused for every request
class ModelManager:
    processor:    WhisperProcessor                = None  # Whisper feature extractor + tokenizer
    model:        WhisperForConditionalGeneration = None  # Whisper model weights
    diarizer:     DiarizationPipeline             = None  # pyannote speaker separator
    device:       str                             = None  # "cuda" or "cpu"
    model_loaded: bool                            = False # flag: True once everything is ready

# Create a single global instance shared across all requests
model_manager = ModelManager()


# Model download helper 
def download_model_if_needed():
    """
    Check if Whisper model is already saved on disk.
    If yes → skip download, return cache path (fast, ~10 seconds to load)
    If no  → download from HuggingFace and save to disk (slow, ~5-10 mins)
    After the first download, this function always takes the fast path.
    """
    # config.json exists in every HuggingFace model repo
    # If it's in our cache folder, the full model was already downloaded
    config_path = os.path.join(CACHE_DIR, "config.json")

    if os.path.exists(config_path):
        # Model already on disk - skip download entirely
        logger.info(f"Whisper model found in cache at {CACHE_DIR} — skipping download")
        return CACHE_DIR

    # Model not cached — download everything from HuggingFace
    logger.info(f"Downloading Whisper model: {MODEL_ID}")
    logger.info("First-time download — takes 5-10 mins but only happens once...")

    # Create the cache directory if it doesn't exist yet
    os.makedirs(CACHE_DIR, exist_ok=True)

    # snapshot_download fetches every file in the HF repo (weights, config, tokenizer)
    # and saves them all to local_dir — after this, config_path will exist
    snapshot_download(
        repo_id   = MODEL_ID,   # your HuggingFace model repo
        local_dir = CACHE_DIR,  # save all files here
        token     = HF_TOKEN,   # needed for private repos
    )

    logger.info(f"Download complete — Whisper model saved to {CACHE_DIR}")
    return CACHE_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Everything before 'yield' runs when the server starts.
    Everything after 'yield' runs when the server shuts down.
    This is where we load both models into memory.
    Loading here (not per-request) means fast response times —
    models are already in memory when the first request arrives.
    """
    logger.info("Server starting up...")
    start = time.time()  # measure total startup time

    # Detect whether a GPU is available — GPU is ~10x faster than CPU for inference
    model_manager.device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Running on: {model_manager.device}")


    # Download model if needed, get the local folder path
    local_model_path = download_model_if_needed()

    logger.info("Loading Whisper processor from cache...")
    # WhisperProcessor.from_pretrained loads from local folder (not HuggingFace URL)
    # local_files_only=True means it will FAIL if files aren't cached — no surprise downloads
    model_manager.processor = WhisperProcessor.from_pretrained(
        local_model_path,
        local_files_only=True,  # never attempt network call — must be on disk
    )

    logger.info("Loading Whisper model weights into GPU memory...")
    model_manager.model = WhisperForConditionalGeneration.from_pretrained(
        local_model_path,
        local_files_only=True, 
        torch_dtype=torch.float16 if model_manager.device == "cuda" else torch.float32,
    ).to(model_manager.device)  # move model to GPU or CPU

    
    model_manager.model.eval()
    logger.info("Whisper model loaded ✓")

    # Step 2: Load pyannote speaker diarization 

    logger.info("Loading pyannote speaker diarization pipeline...")
    # pyannote/speaker-diarization-3.1 (because it can know how many speakers,seperate each persons speach too)
    # use_auth_token is required — pyannote is gated, needs HF account approval
    model_manager.diarizer = DiarizationPipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=HF_TOKEN,
    )

    # Move diarizer to the same device as Whisper (GPU if available)
    model_manager.diarizer = model_manager.diarizer.to(
        torch.device(model_manager.device)
    )
    logger.info("pyannote diarizer loaded ✓")

    # Mark both models as ready  endpoints check this before processing
    model_manager.model_loaded = True

    logger.info(f"Server fully ready in {round(time.time() - start, 2)} seconds")

    # the server runs here, handling requests until shutdown signal
    yield 

    logger.info("Server shutting down — releasing memory...")
    del model_manager.model    
    del model_manager.processor  
    del model_manager.diarizer   
    if model_manager.device == "cuda":
        torch.cuda.empty_cache()  
    logger.info("Shutdown complete")


security = HTTPBearer()

def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != API_KEY:
        # Log unauthorized attempts so we can monitor for attacks
        logger.warning("Unauthorized access attempt — invalid API key")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials  # return key so endpoint knows auth passed

# Core processing function 
def diarize_and_transcribe(audio: np.ndarray, tmp_path: str) -> list:
    logger.info("Running pyannote speaker diarization...")

    # Pass preloaded audio to bypass torchcodec (which fails on Windows when FFmpeg DLLs
    # are missing). pyannote accepts {"waveform": (C, T) tensor, "sample_rate": int}.
    waveform = torch.from_numpy(audio.astype(np.float32))
    if waveform.dim() == 1:
        waveform = waveform.unsqueeze(0)  # (1, samples) for mono
    waveform = waveform.to(model_manager.device)
    audio_input = {"waveform": waveform, "sample_rate": SAMPLE_RATE}

    diarization_output = model_manager.diarizer(audio_input)

    # pyannote v3.1 wraps the result in a DiarizeOutput dataclass
    # We need to unwrap it to get the actual Annotation object
    # hasattr checks if the output has the .speaker_diarization attribute
    if hasattr(diarization_output, "speaker_diarization"):
        # v3.1 API: unwrap the dataclass to get the Annotation
        annotation = diarization_output.speaker_diarization
    else:
        # older API: output is already the Annotation directly
        annotation = diarization_output

    # Step 2: Build segments list 
    segments = []

    # itertracks(yield_label=True) loops over every speaker segment
    # Each iteration gives us:
    #   segment = Segment object with .start and .end (in seconds)
    #   _       = track name (not needed, so we ignore it with _)
    #   speaker = string like "SPEAKER_00" or "SPEAKER_01"
    for segment, _, speaker in annotation.itertracks(yield_label=True):

        # Convert time in seconds to sample index in the numpy array
        # e.g. 2.5 seconds × 16000 samples/sec = sample 40000
        start_sample = int(segment.start * SAMPLE_RATE)
        end_sample   = int(segment.end   * SAMPLE_RATE)

        # Slice the full audio array to get just this speaker's audio
        # audio[40000:80000] = samples from second 2.5 to second 5.0
        speaker_audio = audio[start_sample:end_sample]

        # Skip segments shorter than MIN_DURATION_S (0.5 seconds)
        # Whisper can't meaningfully process very short clips
        if len(speaker_audio) < SAMPLE_RATE * MIN_DURATION_S:
            continue  # skip this segment and move to the next one

        # Add valid segment to the list for translation
        segments.append({
            "speaker": speaker,            # "SPEAKER_00" or "SPEAKER_01"
            "start":   round(segment.start, 2),  # start time in seconds
            "end":     round(segment.end,   2),  # end time in seconds
            "audio":   speaker_audio,      # numpy audio slice for this speaker's turn
        })

    logger.info(f"Diarization found {len(segments)} speaker segments")

    # Fallback: if diarization found no segments (short audio, single speaker), transcribe full audio
    if not segments:
        logger.info("No speaker segments — transcribing full audio as single block")
        min_len = int(SAMPLE_RATE * 0.5)  # skip if < 0.5 sec
        if len(audio) >= min_len:
            segments = [{
                "speaker": "SPEAKER_00",
                "start": 0.0,
                "end": round(len(audio) / SAMPLE_RATE, 2),
                "audio": audio,
            }]

    # Step 3: Translate each speaker segment with Whisper 
    results = []

    for seg in segments:
        # Convert this speaker's raw audio waveform to log-mel spectrogram
        # The spectrogram is the actual input format Whisper understands
        # return_tensors="pt" returns a PyTorch tensor instead of numpy array
        input_features = model_manager.processor.feature_extractor(
            seg["audio"],               # this speaker's audio numpy slice
            sampling_rate  = SAMPLE_RATE,  # must match what Whisper expects
            return_tensors = "pt"       # return as PyTorch tensor
        ).input_features.to(
            device = model_manager.device,  # move to GPU if available
            # Cast to float16 on GPU to match model dtype (avoids type mismatch error)
            # Use float32 on CPU since CPU doesn't handle float16 well
            dtype  = torch.float16 if model_manager.device == "cuda" else torch.float32
        )

        # Run Whisper inference — no_grad() disables gradient tracking
        # (gradients are only needed during training, not inference)
        # This saves memory and speeds up inference
        with torch.no_grad():
            predicted_ids = model_manager.model.generate(
                input_features,
                task           = "translate",  # always output English text
                language       = None,         # auto-detect: Yoruba/Hausa/Igbo/Pidgin/English
                max_new_tokens = 256,          # limit output length to prevent runaway generation
            )

        # Convert predicted token IDs back to readable English string
        # skip_special_tokens=True removes <|endoftext|>, <|translate|> etc.
        # [0] gets the first (and only) result from the batch
        translation = model_manager.processor.tokenizer.batch_decode(
            predicted_ids,
            skip_special_tokens=True
        )[0].strip()  # strip() removes leading/trailing whitespace

        # Add this speaker's translated result to the output list
        results.append({
            "speaker":     seg["speaker"],   # "SPEAKER_00" or "SPEAKER_01"
            "start":       seg["start"],     # when this speaker started talking (seconds)
            "end":         seg["end"],       # when this speaker stopped talking (seconds)
            "translation": translation,      # English translation of what they said
        })

    # Sort segments by start time so transcript reads chronologically
    # key=lambda x: x["start"] sorts by the "start" value of each dict
    results.sort(key=lambda x: x["start"])

    return results  # list of {speaker, start, end, translation} dicts



def format_conversation(segments: list) -> str:
    """
    Convert the list of speaker segments into a readable conversation string.

    Input:  [{"speaker": "SPEAKER_00", "start": 0.5, "end": 8.2, "translation": "Good morning..."}]
    Output: "SPEAKER_00 [0.5s-8.2s]: Good morning, how are you feeling today?"
    """
    lines = []
    for seg in segments:
        # Format each segment as: SPEAKER_XX [start-end]: translation
        lines.append(
            f"{seg['speaker']} [{seg['start']}s\u2013{seg['end']}s]: {seg['translation']}"
        )
    # Join all lines with newline — each speaker turn is on its own line
    return "\n".join(lines)

verify_key=verify_api_key
diarized= diarize_and_transcribe
formated= format_conversation
# """ASR post-processing placeholder.

# Use this module to clean transcripts (punctuation, casing, noise removal)
# after raw speech-to-text conversion.
# """

