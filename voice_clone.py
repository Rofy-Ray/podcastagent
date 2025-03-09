import os
import json
import logging
from elevenlabs.client import ElevenLabs
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def load_voice_config(config_path="voice_config.json"):
    """
    Load voice IDs from configuration file.
    
    Args:
        config_path (str): Path to the configuration file
        
    Returns:
        dict: Dictionary containing voice IDs for males and females
    """
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading voice configuration: {e}")

async def init_client():
    """
    Initialize ElevenLabs client with API key from environment.
    
    Returns:
        ElevenLabs: Initialized ElevenLabs client
    """
    load_dotenv()
    api_key = os.getenv("ELEVENLABS_API_KEY")
    
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY environment variable not set")
    
    return ElevenLabs(api_key=api_key)

async def clone_voice(voice_file, name=None, description=None):
    """
    Clone a voice from an audio file.
    
    Args:
        voice_file (str): Path to the audio file
        name (str, optional): Name for the cloned voice
        description (str, optional): Description for the cloned voice
        
    Returns:
        Voice: Cloned voice object that can be used with generate()
    """
    client = await init_client()
    
    if not name:
        name = os.path.splitext(os.path.basename(voice_file))[0]
    
    if not description:
        description = f"Cloned voice from {voice_file}"
    
    try:
        voice = client.clone(
            name=name,
            description=description,
            files=[voice_file],
        )
        return voice
    except Exception as e:
        logger.error(f"Error cloning voice: {e}")
        raise