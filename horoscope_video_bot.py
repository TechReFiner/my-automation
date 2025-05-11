import requests
from google.cloud import texttospeech
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, TextClip, concatenate_videoclips
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import os
import json
import base64
import time # For adding delays if needed

# --- Configuration ---
# These will be loaded from environment variables in GitHub Actions
# For local testing, you might set them directly or use a.env file with python-dotenv

# Google Cloud Service Account JSON content (for TTS)
# For local testing, set GOOGLE_APPLICATION_CREDENTIALS env var to the path of your service account JSON file
# In GitHub Actions, we'll load the JSON content from a secret
GOOGLE_CREDENTIALS_JSON_CONTENT = os.environ.get('GOOGLE_CREDENTIALS_JSON_CONTENT')

# YouTube OAuth client_secret.json content
YOUTUBE_CLIENT_SECRET_JSON_CONTENT = os.environ.get('YOUTUBE_CLIENT_SECRET_JSON_CONTENT')

# YouTube token.pickle content (Base64 encoded)
YOUTUBE_TOKEN_PICKLE_BASE64 = os.environ.get('YOUTUBE_TOKEN_PICKLE_BASE64')

# Paths (adjust as needed)
OUTPUT_DIR = "output"
IMAGE_DIR = "images" # Store your 12 zodiac sign images here (e.g., aries.jpg, taurus.jpg)
CLIENT_SECRETS_FILE_TEMP = os.path.join(OUTPUT_DIR, "client_secret.json")
TOKEN_PICKLE_FILE_TEMP = os.path.join(OUTPUT_DIR, "token.pickle")
SERVICE_ACCOUNT_FILE_TEMP = os.path.join(OUTPUT_DIR, "service_account.json")


ZODIAC_SIGNS = ["aries", "taurus", "gemini", "cancer", "leo", "virgo",
                "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces"]

# --- Helper Functions ---

def setup_credentials():
    """Sets up credential files from environment variables for GitHub Actions."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if GOOGLE_CREDENTIALS_JSON_CONTENT:
        with open(SERVICE_ACCOUNT_FILE_TEMP, 'w') as f:
            f.write(GOOGLE_CREDENTIALS_JSON_CONTENT)
        os.environ = SERVICE_ACCOUNT_FILE_TEMP
        print("Google Cloud service account credentials set up from environment variable.")

    if YOUTUBE_CLIENT_SECRET_JSON_CONTENT:
        with open(CLIENT_SECRETS_FILE_TEMP, 'w') as f:
            f.write(YOUTUBE_CLIENT_SECRET_JSON_CONTENT)
        print("YouTube client_secret.json set up from environment variable.")

    if YOUTUBE_TOKEN_PICKLE_BASE64:
        try:
            decoded_token = base64.b64decode(YOUTUBE_TOKEN_PICKLE_BASE64)
            with open(TOKEN_PICKLE_FILE_TEMP, 'wb') as token_file:
                token_file.write(decoded_token)
            print("YouTube token.pickle set up from environment variable.")
        except Exception as e:
            print(f"Error decoding or writing token.pickle: {e}")
            # If token is invalid, YouTube auth will likely fail or prompt for re-auth.
            # For a fully automated script, this means the initial auth needs to be redone
            # and the secret updated if the refresh token becomes invalid.


def fetch_horoscope(sign):
    """Fetches horoscope for a given sign from Aztro API."""
    try:
        # Aztro API can be sometimes unreliable or slow. Add timeout.
        response = requests.post(f"https://aztro.sameerkumar.website/?sign={sign}&day=today", timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"Fetched horoscope for {sign}: {data.get('description')[:50]}...")
        return data.get('description', "Could not fetch horoscope today.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching horoscope for {sign}: {e}")
        return f"Apologies, {sign}. We couldn't retrieve your horoscope at this moment."

def regenerate_text(text, sign):
    """Basic text regeneration (placeholder). Enhance as needed."""
    # Example: Add a simple intro/outro
    # For more advanced regeneration, consider NLP libraries or APIs,
    # but be mindful of complexity and processing time for free schedulers.
    return f"Hello {sign.capitalize()}, your horoscope for today: {text} Have a wonderful day!"

def text_to_speech_google(text_input, output_filepath, voice_name="en-US-Neural2-A"):
    """Converts text to speech using Google Cloud TTS and saves as MP3."""
    try:
        client = texttospeech.TextToSpeechClient() # Assumes GOOGLE_APPLICATION_CREDENTIALS is set
        synthesis_input = texttospeech.SynthesisInput(text=text_input)
        voice = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name=voice_name
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        with open(output_filepath, "wb") as out_file:
            out_file.write(response.audio_content)
        print(f"Audio content written to file: {output_filepath}")
        return True
    except Exception as e:
        print(f"Error in text_to_speech_google: {e}")
        return False

def create_segment_video(sign_name, horoscope_text, image_path, audio_path, segment_duration):
    """Creates a video segment for one zodiac sign."""
    try:
        # Create TextClip for the horoscope text
        # Adjust font, fontsize, color, size, position as needed
        txt_clip = TextClip(horoscope_text, fontsize=30, color='white', font='Arial-Bold',
                            size=(1200, 200), method='caption', align='West', bg_color='transparent')
        txt_clip = txt_clip.set_position(('center', 0.75), relative=True).set_duration(segment_duration)

        # Create TextClip for the Sign Name
        sign_title_clip = TextClip(sign_name.capitalize(), fontsize=70, color='yellow', font='Arial-Bold',
                                   stroke_color='black', stroke_width=2)
        sign_title_clip = sign_title_clip.set_position(('center', 0.1), relative=True).set_duration(segment_duration)


        image_clip = ImageClip(image_path).set_duration(segment_duration).resize(height=720) # Assuming 720p height
        # Ensure image is 1280x720 or similar 16:9 aspect ratio
        # If image is not 16:9, you might need to add padding or crop
        image_clip = image_clip.set_position('center')


        audio_clip = AudioFileClip(audio_path)
        if audio_clip.duration > segment_duration: # If audio is longer, truncate segment
            audio_clip = audio_clip.subclip(0, segment_duration)
        elif audio_clip.duration < segment_duration: # If audio is shorter, this might be an issue or loop audio
             # For simplicity, we'll use the audio's duration if it's shorter than planned segment_duration
             # This means segment_duration passed to this function should ideally be audio_clip.duration
             pass


        video_segment = CompositeVideoClip([image_clip, sign_title_clip, txt_clip], size=(1280, 720))
        video_segment = video_segment.set_audio(audio_clip)
        video_segment = video_segment.set_duration(audio_clip.duration) # Ensure segment duration matches audio

        print(f"Created video segment for {sign_name} with duration {video_segment.duration:.2f}s")
        return video_segment

    except Exception as e:
        print(f"Error creating video segment for {sign_name}: {e}")
        # Fallback: create a simple image clip if text or audio fails
        try:
            audio_clip_fallback = AudioFileClip(audio_path)
            image_clip_fallback = ImageClip(image_path).set_duration(audio_clip_fallback.duration).resize(height=720)
            image_clip_fallback = image_clip_fallback.set_position('center')
            video_segment_fallback = CompositeVideoClip([image_clip_fallback], size=(1280,720)).set_audio(audio_clip_fallback)
            return video_segment_fallback
        except Exception as fallback_e:
            print(f"Fallback video creation also failed for {sign_name}: {fallback_e}")
            return None


def get_youtube_service():
    """Authenticates and returns a YouTube service object."""
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(TOKEN_PICKLE_FILE_TEMP):
        with open(TOKEN_PICKLE_FILE_TEMP, 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Failed to refresh token: {e}. Need to re-authenticate.")
                creds = None # Force re-authentication
        if not creds: # creds is None if refresh failed or no token.pickle
            if not os.path.exists(CLIENT_SECRETS_FILE_TEMP):
                print(f"ERROR: YouTube client secrets file ({CLIENT_SECRETS_FILE_TEMP}) not found.")
                print("Ensure YOUTUBE_CLIENT_SECRET_JSON_CONTENT env var is set in GitHub Actions,")
                print("or the file exists locally for the initial auth run.")
                return None
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRETS_FILE_TEMP, ['https://www.googleapis.com/auth/youtube.upload'])
                # For an automated script, run_local_server is problematic.
                # The initial run MUST be done manually where a browser can be opened.
                # Subsequent runs in GitHub Actions will rely on the generated token.pickle.
                # If this part is reached in GitHub Actions, it means token.pickle is missing/invalid.
                print("Attempting to run console auth. This requires manual interaction.")
                print("If running in GitHub Actions and this message appears, the YOUTUBE_TOKEN_PICKLE_BASE64 secret is likely missing or invalid.")
                creds = flow.run_console() # Use run_console for non-GUI environments if needed for initial auth
            except Exception as e:
                print(f"Error during YouTube OAuth flow: {e}")
                return None
        # Save the credentials for the next run
        if creds:
            with open(TOKEN_PICKLE_FILE_TEMP, 'wb') as token:
                pickle.dump(creds, token)
            # If running locally for the first time, you'll need to get this newly created
            # TOKEN_PICKLE_FILE_TEMP, base64 encode it, and set it as a GitHub Secret.
            print(f"Credentials saved to {TOKEN_PICKLE_FILE_TEMP}. If this is the first auth,")
            print("you need to Base64 encode this file and update the YOUTUBE_TOKEN_PICKLE_BASE64 GitHub Secret.")

    if not creds:
        print("Failed to obtain YouTube credentials.")
        return None

    return build('youtube', 'v3', credentials=creds)


def upload_video_to_youtube(youtube_service, file_path, title, description, tags, category_id="24", privacy_status="private"):
    """Uploads a video to YouTube."""
    try:
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': category_id # 24 = Entertainment, 22 = People & Blogs
            },
            'status': {
                'privacyStatus': privacy_status # 'public', 'private', or 'unlisted'
            }
        }
        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
        request = youtube_service.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media
        )
        response = None
        print(f"Uploading {file_path} to YouTube...")
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
        print(f"Video uploaded successfully! Video ID: {response['id']}")
        return response['id']
    except Exception as e:
        print(f"Error uploading video to YouTube: {e}")
        return None

# --- Main Execution ---
def main():
    print("Starting daily horoscope video generation process...")
    setup_credentials() # Load credentials from env vars if in GitHub Actions

    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True) # Ensure image directory exists

    all_video_segments =
    youtube_description_parts =
    current_timestamp_seconds = 0

    for sign in ZODIAC_SIGNS:
        print(f"\n--- Processing {sign.capitalize()} ---")
        raw_horoscope = fetch_horoscope(sign)
        if not raw_horoscope or "Could not fetch" in raw_horoscope or "couldn't retrieve" in raw_horoscope :
            print(f"Skipping {sign} due to fetch error.")
            # Add a placeholder to keep video timing consistent or skip
            # For simplicity, we'll skip if fetch fails badly.
            # You might want a default "unavailable" segment.
            continue

        regenerated_horoscope = regenerate_text(raw_horoscope, sign)

        audio_filename = f"{sign}_horoscope.mp3"
        audio_filepath = os.path.join(OUTPUT_DIR, audio_filename)

        if not text_to_speech_google(regenerated_horoscope, audio_filepath):
            print(f"Skipping {sign} due to TTS error.")
            continue

        # Ensure the image exists
        image_filename = f"{sign.lower()}.jpg" # Or.png, etc.
        image_filepath = os.path.join(IMAGE_DIR, image_filename)
        if not os.path.exists(image_filepath):
            print(f"ERROR: Image for {sign} not found at {image_filepath}. Please add it.")
            # Create a placeholder image or use a default
            # For now, we'll try to create a segment without a specific image if it's missing
            # by using a default placeholder image if you have one, or skip.
            # This example will fail if image is missing.
            # You should have 12 images: aries.jpg, taurus.jpg, etc. in the IMAGE_DIR.
            print(f"Please create an image at: {image_filepath}")
            # As a simple fallback, let's try to use a generic image if the specific one is missing
            generic_image_path = os.path.join(IMAGE_DIR, "default.jpg")
            if os.path.exists(generic_image_path):
                image_filepath = generic_image_path
            else:
                print(f"Default image {generic_image_path} also not found. Skipping video segment for {sign}.")
                continue


        # The duration of the segment will be determined by the audio
        temp_audio_clip = AudioFileClip(audio_filepath)
        segment_duration = temp_audio_clip.duration + 1.0 # Add 1 sec pause/buffer
        temp_audio_clip.close()


        # Create the video segment for this sign
        # Pass the horoscope text itself for the TextClip
        video_segment = create_segment_video(sign, regenerated_horoscope, image_filepath, audio_filepath, segment_duration)

        if video_segment:
            all_video_segments.append(video_segment)
            # For YouTube chapters in description
            minutes = int(current_timestamp_seconds // 60)
            seconds = int(current_timestamp_seconds % 60)
            youtube_description_parts.append(f"{minutes:02d}:{seconds:02d} {sign.capitalize()}")
            current_timestamp_seconds += video_segment.duration
        else:
            print(f"Failed to create video segment for {sign}.")

        # Clean up individual audio file
        # if os.path.exists(audio_filepath):
        #     os.remove(audio_filepath)

    if not all_video_segments:
        print("No video segments were created. Exiting.")
        return

    # Concatenate all segments into one video
    final_video_clip = concatenate_videoclips(all_video_segments, method="compose")
    final_video_filename = "daily_horoscope_compilation.mp4"
    final_video_filepath = os.path.join(OUTPUT_DIR, final_video_filename)

    try:
        print(f"Writing final consolidated video to {final_video_filepath}...")
        final_video_clip.write_videofile(
            final_video_filepath,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile='temp-audio.m4a', # Recommended for some systems
            remove_temp=True
        )
        print("Final video created successfully.")
    except Exception as e:
        print(f"Error writing final video: {e}")
        return
    finally:
        # Close all clips
        for segment in all_video_segments:
            if segment.audio:
                segment.audio.close()
            # MoviePy ImageClips don't always need explicit closing like audio/video files
        if final_video_clip.audio: # Check if audio exists before trying to close
            final_video_clip.audio.close()


    # Upload to YouTube
    youtube_service = get_youtube_service()
    if youtube_service and os.path.exists(final_video_filepath):
        today_date = time.strftime("%B %d, %Y")
        video_title = f"Daily Horoscope Compilation - {today_date}"
        video_description = "\n".join(youtube_description_parts)
        video_tags = ["horoscope", "astrology", "daily horoscope", "zodiac"] + ZODIAC_SIGNS
        
        upload_video_to_youtube(youtube_service, final_video_filepath, video_title, video_description, video_tags, privacy_status="public") # Set to 'public' when ready
    elif not youtube_service:
        print("Could not get YouTube service. Video will not be uploaded.")
    elif not os.path.exists(final_video_filepath):
        print(f"Final video file {final_video_filepath} not found. Cannot upload.")

    # Clean up temporary credential files if they were created from env vars
    if GOOGLE_CREDENTIALS_JSON_CONTENT and os.path.exists(SERVICE_ACCOUNT_FILE_TEMP):
        os.remove(SERVICE_ACCOUNT_FILE_TEMP)
    if YOUTUBE_CLIENT_SECRET_JSON_CONTENT and os.path.exists(CLIENT_SECRETS_FILE_TEMP):
        os.remove(CLIENT_SECRETS_FILE_TEMP)
    if YOUTUBE_TOKEN_PICKLE_BASE64 and os.path.exists(TOKEN_PICKLE_FILE_TEMP):
        os.remove(TOKEN_PICKLE_FILE_TEMP)

    print("\nDaily horoscope video generation process finished.")

if __name__ == "__main__":
    main()
