from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
import os
import uuid
import logging
from TTS.api import TTS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- Configuration ---
VOICES_DIR = "voices"
CLONED_DIR = "cloned"
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
USE_GPU = True # IMPORTANT: Requires a GPU instance on Runpod

# --- Initialization ---
try:
    # Ensure folders exist
    os.makedirs(VOICES_DIR, exist_ok=True)
    os.makedirs(CLONED_DIR, exist_ok=True)
    logger.info(f"Created directories: {VOICES_DIR}, {CLONED_DIR}")

    # Load XTTS model
    # NOTE: Model files will be downloaded on first run, which can take time.
    logger.info(f"Loading TTS model: {MODEL_NAME} (GPU: {USE_GPU})...")
    tts = TTS(model_name=MODEL_NAME, gpu=USE_GPU)
    logger.info("TTS model loaded successfully.")

except Exception as e:
    logger.error(f"Fatal error during initialization: {e}", exc_info=True)
    # If the model fails to load, the app can't function.
    # You might want to handle this more gracefully depending on requirements.
    raise RuntimeError(f"Could not initialize TTS model: {e}") from e

# --- API Endpoints ---

@app.post("/record_voice")
async def record_voice(audio: UploadFile = File(...), user_id: str = Form(...)):
    """
    Receives an audio file upload and saves it as a voice sample for a user.
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id form field is required.")
    if not audio.filename:
         raise HTTPException(status_code=400, detail="No file uploaded or filename missing.")

    # Basic validation for file extension (optional but good practice)
    allowed_extensions = {".wav", ".mp3", ".ogg"} # Add others if needed
    file_ext = os.path.splitext(audio.filename)[1].lower()
    if file_ext not in allowed_extensions:
         raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}")

    try:
        # Create a unique filename
        filename = f"{user_id}_{uuid.uuid4()}{file_ext}" # Keep original extension if possible
        file_path = os.path.join(VOICES_DIR, filename)

        logger.info(f"Receiving voice for user '{user_id}'. Saving to '{file_path}'")

        # Save the uploaded file
        with open(file_path, "wb") as f:
            content = await audio.read()
            f.write(content)

        logger.info(f"Successfully saved voice file: {file_path}")
        return {"message": "Voice recorded successfully", "file_path_on_server": file_path} # Return path on server for debugging/logging

    except Exception as e:
        logger.error(f"Error saving voice file for user '{user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not save voice file.")


@app.post("/clone_voice")
async def clone_voice(user_id: str = Form(...), text: str = Form(...)):
    """
    Generates cloned speech based on the latest voice sample for a user and input text.
    """
    if not user_id or not text:
         raise HTTPException(status_code=400, detail="user_id and text form fields are required.")

    try:
        # Find the latest voice sample for the user (simple approach: sort by name)
        user_files = sorted([f for f in os.listdir(VOICES_DIR) if f.startswith(f"{user_id}_")])
        if not user_files:
            logger.warning(f"No voice samples found for user_id: {user_id}")
            raise HTTPException(status_code=404, detail="No voice recorded for this user_id")

        voice_sample_path = os.path.join(VOICES_DIR, user_files[-1]) # Use the latest file
        output_filename = f"cloned_{user_id}_{uuid.uuid4()}.wav"
        output_path = os.path.join(CLONED_DIR, output_filename)

        logger.info(f"Cloning voice for user '{user_id}' using sample '{voice_sample_path}'. Output: '{output_path}'")
        logger.info(f"Input text: '{text[:50]}...'") # Log beginning of text

        # Perform the TTS cloning
        # Add error handling for the TTS process itself
        try:
            tts.tts_to_file(
                text=text,
                speaker_wav=voice_sample_path,
                language="en", # Hardcoded for now
                file_path=output_path,
            )
        except Exception as e:
             logger.error(f"TTS generation failed for user '{user_id}': {e}", exc_info=True)
             raise HTTPException(status_code=500, detail=f"Voice cloning process failed: {e}")

        logger.info(f"Successfully generated cloned audio: {output_path}")

        # Return a URL that the client can use to fetch the audio
        # Assumes the /audio/ endpoint is correctly set up
        audio_url = f"/audio/{output_filename}"
        return {"audio_url": audio_url}

    except HTTPException as http_exc:
        # Re-raise HTTPExceptions directly
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error during voice cloning for user '{user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred during voice cloning.")


@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """
    Serves a previously generated audio file.
    """
    file_path = os.path.join(CLONED_DIR, filename)

    # Security check: Prevent path traversal attacks
    if not filename or ".." in filename or filename.startswith("/"):
         raise HTTPException(status_code=400, detail="Invalid filename.")

    if os.path.exists(file_path):
        logger.info(f"Serving audio file: {file_path}")
        return FileResponse(file_path, media_type="audio/wav")
    else:
        logger.warning(f"Audio file not found: {file_path}")
        raise HTTPException(status_code=404, detail="Audio file not found")


@app.get("/")
async def health_check():
    """
    Simple health check endpoint.
    """
    logger.debug("Health check endpoint called.")
    return {"status": "running", "message": "TTS API is operational."}

# --- Optional: Add main execution block for direct running (though uvicorn is preferred) ---
# if __name__ == "__main__":
#     import uvicorn
#     logger.info("Starting server directly with uvicorn...")
#     uvicorn.run(app, host="0.0.0.0", port=8000)