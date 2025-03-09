import re
import io
import os
import json
import random
import logging
import tempfile
from datetime import datetime
from elevenlabs.client import ElevenLabs, VoiceSettings, Voice
from pydub import AudioSegment
from dotenv import load_dotenv
from voice_clone import init_client, load_voice_config, clone_voice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def preprocess_transcript(transcript, host_name, guest_name):
    """
    Clean and preprocess the transcript for TTS conversion.
    
    Args:
        transcript (str): Raw transcript text
        host_name (str): Name of the host
        guest_name (str): Name of the guest
    
    Returns:
        list: Cleaned conversation entries
    """
    transcript = re.sub(r'\*+', '', transcript)
    
    lines = transcript.split('\n')
    conversations = []
    
    for line in lines:
        line = line.strip()
        
        if not line:
            continue
        
        if line.startswith(f"{host_name}:"):
            conversations.append({
                'role': 'host',
                'text': line.replace(f"{host_name}:", '').strip()
            })
        elif line.startswith(f"{guest_name}:"):
            conversations.append({
                'role': 'guest',
                'text': line.replace(f"{guest_name}:", '').strip()
            })
    
    return conversations

async def select_voice_id(gender, config=None):
    """
    Select a random voice ID based on gender.
    
    Args:
        gender (str): 'male' or 'female'
        config (dict, optional): Voice configuration dictionary
        
    Returns:
        str: Selected voice ID
    """
    if config is None:
        config = await load_voice_config()
        
    gender = gender.lower()
    if gender == 'male':
        return random.choice(config['males'])
    elif gender == 'female':
        return random.choice(config['females'])
    else:
        raise ValueError("Gender must be 'male' or 'female'")

async def setup_voices(host_voice=None, host_gender=None, guest_voice=None, guest_gender=None):
    """
    Set up voice configurations for host and guest.
    
    Args:
        host_voice (Voice, optional): Cloned voice for host
        host_gender (str, optional): Gender of host ('male' or 'female')
        guest_voice (Voice, optional): Cloned voice for guest
        guest_gender (str, optional): Gender of guest ('male' or 'female')
        
    Returns:
        dict: Voice configuration for host and guest
    """
    config = await load_voice_config()
    
    host_voice_settings = VoiceSettings(
        stability=0.45,
        similarity_boost=0.75,
        style=0.30,
        use_speaker_boost=True
    )
    
    guest_voice_settings = VoiceSettings(
        stability=0.50,
        similarity_boost=0.65,
        style=0.40,
        use_speaker_boost=True
    )
    
    voices = {
        'host': {
            'voice': host_voice,
            'voice_id': await select_voice_id(host_gender, config) if host_gender else None,
            'voice_settings': host_voice_settings
        },
        'guest': {
            'voice': guest_voice,
            'voice_id': await select_voice_id(guest_gender, config) if guest_gender else None,
            'voice_settings': guest_voice_settings
        }
    }
    
    return voices

async def generate_podcast_audio(transcript, host_voice=None, host_gender=None, 
                          guest_voice=None, guest_gender=None, 
                          host_name="Host", guest_name="Guest"):
    """
    Generate audio for podcast conversations.
    
    Args:
        transcript (str): Raw transcript text
        host_voice (Voice, optional): Cloned voice for host
        host_gender (str, optional): Gender of host ('male' or 'female')
        guest_voice (Voice, optional): Cloned voice for guest
        guest_gender (str, optional): Gender of guest ('male' or 'female')
        host_name (str): Name of the host
        guest_name (str): Name of the guest
    
    Returns:
        tuple: Filename and full path of generated audio
    """
    client = await init_client()
    
    conversations = await preprocess_transcript(transcript, host_name, guest_name)
    logger.debug(f"Processing {len(conversations)} conversation segments")
    
    if not conversations:
        logger.error("Empty conversations list from transcript")
        raise ValueError("No conversation segments found in transcript")
    
    voices = await setup_voices(host_voice, host_gender, guest_voice, guest_gender)
    
    combined_audio = AudioSegment.empty()
    
    for entry in conversations:
        role = entry['role']
        text = entry['text']
        
        if voices[role]['voice']:
            voice_obj = voices[role]['voice']
            current_speaker = host_name if role == 'host' else guest_name
        else:
            voice_id = voices[role]['voice_id']
            settings = voices[role]['voice_settings']
            voice_obj = Voice(voice_id=voice_id, settings=settings)
            current_speaker = host_name if role == 'host' else guest_name
        
        try:
            audio_response = client.generate(
                text=text,
                voice=voice_obj,
                model="eleven_multilingual_v2"
            )
            
            buffer = io.BytesIO()
            
            for chunk in audio_response:
                if chunk:
                    buffer.write(chunk)
                else:
                    logger.warning("Received empty audio chunk")
                    
            if buffer.tell() == 0:
                raise ValueError(f"No audio data generated for {current_speaker}")
            
            buffer.seek(0)
            
            try:
                audio_segment = AudioSegment.from_file(buffer, format="mp3")
            except Exception as e:
                logger.error("Failed to parse audio buffer", exc_info=True)
                raise ValueError(f"Invalid audio data for {current_speaker}") from e
            
            combined_audio += audio_segment
            logger.info(f"Added {len(audio_segment)}ms audio for {current_speaker}")
                        
            delay_duration = random.uniform(0.2, 0.5) * 1000  
            combined_audio += AudioSegment.silent(duration=delay_duration)
                    
        except Exception as e:
            logger.error(f"Error generating audio for {current_speaker}", exc_info=True)
            raise e
        
    if len(combined_audio) == 0:
        raise ValueError("Failed to generate any audio content")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{host_name}_conversation_with_{guest_name}.mp3"
    
    temp_file_path = tempfile.mktemp(suffix=".mp3")
    
    combined_audio.export(temp_file_path, format="mp3")
    
    logger.info(f"Audio file saved to {temp_file_path}")
    return filename, temp_file_path

async def setup_voice_for_role(role, voice_file, gender):
    """
    Set up a voice for a specific role (host or guest).
    
    Args:
        role (str): 'host' or 'guest'
        voice_file (str): Path to voice audio file for cloning
        gender (str): 'male' or 'female' for fallback voice selection
        
    Returns:
        tuple: (Voice object from cloning, gender for fallback)
    """    
    if role not in ['host', 'guest']:
        raise ValueError("Role must be 'host' or 'guest'")
    
    if gender is None:
        gender = random.choice(["male", "female"])
    
    if gender not in ['male', 'female']:
        raise ValueError("Gender must be 'male' or 'female'")
    
    try:
        if voice_file and os.path.exists(voice_file):
            name = f"{role.capitalize()} Voice"
            description = f"Cloned voice for {role}"
            voice = await clone_voice(voice_file, name, description)
            return voice, gender
        else:
            return None, gender
    except Exception as e:
        logger.error(f"Error setting up voice for {role}: {e}")
        return None, gender