import os
import uuid
import asyncio
import logging
from typing import Dict, Any, List, Optional
import io
import boto3
import json
import base64
import random
import tempfile
from pydantic import BaseModel, Field, ValidationError
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from langgraph.checkpoint.memory import MemorySaver
from graph import podcast_builder
from podcast_generator import setup_voice_for_role, generate_podcast_audio
from aws_config import upload_to_s3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Podcast Generator API", 
              description="Generate AI podcasts with customizable voices",
              version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ApiKeys(BaseModel):
    openai: str
    anthropic: str
    tavily: str
    elevenlabs: str

class EnsoInput(BaseModel):
    business_description: str
    business_name: str
    email: str
    logo: Optional[str] = None
    color_palette: Optional[List[str]] = None
    api_keys: ApiKeys

class UserInput(BaseModel):
    topic: str
    host_name: str
    guest_name: str
    role: str 
    host_voice_file: Optional[str] = None
    guest_voice_file: Optional[str] = None
    host_gender: Optional[str] = None
    guest_gender: Optional[str] = None

class RequestPayload(BaseModel):
    execution_id: str
    inputs: Dict[str, Any]
    webhook_url: Optional[str] = None

class ResultResponseItem(BaseModel):
    type: str  
    url: Optional[str] = None
    text: Optional[str] = None
    list: Optional[List[str]] = None

class ResponsePayload(BaseModel):
    execution_id: str
    status: str
    message: str
    results: List[ResultResponseItem]

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[str] = None

def set_api_keys(api_keys):
    """Set API keys as environment variables (temporarily for this request)"""
    os.environ["OPENAI_API_KEY"] = api_keys.openai
    os.environ["ANTHROPIC_API_KEY"] = api_keys.anthropic
    os.environ["TAVILY_API_KEY"] = api_keys.tavily
    os.environ["ELEVENLABS_API_KEY"] = api_keys.elevenlabs

async def process_podcast_request(payload: RequestPayload) -> ResponsePayload:
    """Process the podcast generation request"""
    execution_id = payload.execution_id
    enso_input = EnsoInput(**payload.inputs.get("enso_input", {}))
    user_input = UserInput(**payload.inputs.get("user_input", {}))
    webhook_url = payload.webhook_url
    
    set_api_keys(enso_input.api_keys)
    
    temp_files = []
        
    try:
        topic = user_input.topic
        host_name = user_input.host_name
        guest_name = user_input.guest_name
        role = user_input.role
        
        host_voice_file = user_input.host_voice_file if role == "host" else None
        guest_voice_file = user_input.guest_voice_file if role == "guest" else None
        
        host_gender = user_input.host_gender or random.choice(["male", "female"])
        guest_gender = user_input.guest_gender or random.choice(["male", "female"])
        
        filename, audio_path = await run_podcast_generator(
            topic=topic,
            host_voice_file=host_voice_file,
            host_gender=host_gender,
            guest_voice_file=guest_voice_file,
            guest_gender=guest_gender,
            host_name=host_name,
            guest_name=guest_name
        )
        
        temp_files.append(audio_path)
                
        s3_url = await upload_to_s3(audio_path, "genaipods", f"podcasts/{filename}", expiration=3600)
        
        if os.path.exists(audio_path):
            os.remove(audio_path)
            logger.info(f"Temporary file {audio_path} removed")
        
        results = [
            ResultResponseItem(
                type="audio",
                url=s3_url,
                text=f"AI Podcast featuring {host_name} and {guest_name} discussing {topic}",
                list=None
            ),
            ResultResponseItem(
                type="text",
                url=None,
                text=f"Generated AI podcast on '{topic}' with {host_name} as host and {guest_name} as guest",
                list=None
            )
        ]
        
        response = ResponsePayload(
            execution_id=execution_id,
            status="success",
            message="Podcast generated successfully",
            results=results
        )
        
        if webhook_url:
            import requests
            try:
                requests.post(webhook_url, json=response.model_dump())
            except Exception as e:
                logger.error(f"Failed to POST to webhook: {str(e)}")
        
        return response
    
    except Exception as e:
        logger.error(f"Error generating podcast: {e}")
        error_response = ResponsePayload(
            execution_id=execution_id,
            status="error",
            message=f"Failed to generate podcast: {str(e)}",
            results=[]
        )
        
        if webhook_url:
            import requests
            try:
                requests.post(webhook_url, json=error_response.dict())
            except Exception as webhook_err:
                logger.error(f"Failed to POST to webhook: {str(webhook_err)}")
        
        return error_response
    
    finally:
        for file_path in temp_files:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Temporary file {file_path} removed")
                except Exception as e:
                    logger.error(f"Failed to remove temporary file {file_path}: {str(e)}")

async def run_podcast_generator(topic, 
                               host_voice_file=None, host_gender=None,
                               guest_voice_file=None, guest_gender=None,
                               host_name="Host", guest_name="Guest"):
    """
    Run the podcast generation pipeline.
    
    Args:
        topic (str): Topic for the podcast
        host_voice_file (str, optional): Path to host voice file for cloning
        host_gender (str): Gender of host ('male' or 'female')
        guest_voice_file (str, optional): Path to guest voice file for cloning
        guest_gender (str): Gender of guest ('male' or 'female')
        host_name (str): Name of the host
        guest_name (str): Name of the guest
        
    Returns:
        tuple: Filename and path of the generated podcast audio
    """
    host_gender = host_gender or random.choice(["male", "female"])
    guest_gender = guest_gender or random.choice(["male", "female"])
    
    memory = MemorySaver()
    graph = podcast_builder.compile(checkpointer=memory)
    thread = {"configurable": {"thread_id": str(uuid.uuid4())}}
    
    host_voice, host_gender = await setup_voice_for_role('host', host_voice_file, host_gender)
    guest_voice, guest_gender = await setup_voice_for_role('guest', guest_voice_file, guest_gender)
    
    logger.info(f"Generating podcast on topic: {topic}")
    async for event in graph.astream({"topic": topic, "host": host_name, "guest": guest_name}, thread, stream_mode="updates"):
        logger.info(event)
    
    final_state = graph.get_state(thread)
    transcript = final_state.values.get('final_transcript')
    
    if not transcript:
        raise ValueError("Failed to generate transcript")
    
    logger.info("Transcript generated. Creating audio...")
    
    filename, audio_path = await generate_podcast_audio(
        transcript,
        host_voice=host_voice,
        host_gender=host_gender,
        guest_voice=guest_voice,
        guest_gender=guest_gender,
        host_name=host_name,
        guest_name=guest_name
    )
    
    logger.info(f"Podcast generated: {filename}")
    return filename, audio_path
        
async def save_uploaded_file(file: UploadFile) -> str:
    """Save an uploaded file to disk and return the full path"""
    try:
        temp_dir = os.path.join(tempfile.gettempdir(), "voice_file_uploads")
        os.makedirs(temp_dir, exist_ok=True)
        
        filename = f"{uuid.uuid4().hex}_{file.filename}"
        file_path = os.path.join(temp_dir, filename)
        
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
            
        logger.info(f"Successfully saved uploaded file to {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error saving uploaded file: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to save uploaded file: {str(e)}")
        
async def save_base64_file(base64_data: str) -> str:
    """Save a base64 encoded file to disk and return the full path"""
    try:
        temp_dir = os.path.join(tempfile.gettempdir(), "voice_file_uploads")
        os.makedirs(temp_dir, exist_ok=True)
        
        if "base64," in base64_data:
            base64_data = base64_data.split("base64,")[1]
        
        filename = f"{uuid.uuid4().hex}.mp3"
        file_path = os.path.join(temp_dir, filename)
        
        content = base64.b64decode(base64_data)
        with open(file_path, "wb") as f:
            f.write(content)
            
        logger.info(f"Successfully saved base64 file to {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error saving base64 file: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to save base64 file: {str(e)}")

async def cleanup_files(json_data: dict):
    """Clean up any temporary files created during request processing"""
    try:
        if 'inputs' in json_data and 'user_input' in json_data['inputs']:
            user_input = json_data['inputs']['user_input']
            for file_key in ['host_voice_file', 'guest_voice_file']:
                if file_key in user_input and isinstance(user_input[file_key], str):
                    file_path = user_input[file_key]
                    if os.path.exists(file_path):
                        os.unlink(file_path)
                        logger.info(f"Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.error(f"Error during file cleanup: {str(e)}", exc_info=True)
        
@app.post("/generate-podcast", response_model=ResponsePayload)
async def generate_podcast(request: Request, background_tasks: BackgroundTasks):
    """
    Handle podcast generation with both JSON fields and binary files
    """
    logger.info("Received request for podcast generation")
    
    content_type = request.headers.get('Content-Type', '')
    
    json_data = {}
    files = {}
    
    if content_type.startswith('multipart/form-data'):
        form_data = await request.form()
        
        for key in form_data:
            if key != 'host_voice_file' and key != 'guest_voice_file':
                json_value = form_data[key]
                if isinstance(json_value, str):
                    try:
                        json_data = json.loads(json_value)
                        break 
                    except json.JSONDecodeError:
                        continue
        
        if not json_data:
            try:
                json_data = {}
                if 'execution_id' in form_data:
                    json_data['execution_id'] = form_data['execution_id']
                
                if 'inputs' not in json_data:
                    json_data['inputs'] = {}
                
                if 'webhook_url' in form_data:
                    json_data['webhook_url'] = form_data['webhook_url']
                
                if 'execution_id' not in json_data:
                    raise HTTPException(status_code=400, detail="Missing required execution_id in request")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid request format: {str(e)}")
        
        if 'inputs' not in json_data:
            json_data['inputs'] = {}
        if 'user_input' not in json_data['inputs']:
            json_data['inputs']['user_input'] = {}
        
        if 'host_voice_file' in form_data:
            file = form_data['host_voice_file']
            if isinstance(file, UploadFile):
                file_path = await save_uploaded_file(file)
                json_data['inputs']['user_input']['host_voice_file'] = file_path
                logger.info(f"Saved host voice file to {file_path}")
        
        if 'guest_voice_file' in form_data:
            file = form_data['guest_voice_file']
            if isinstance(file, UploadFile):
                file_path = await save_uploaded_file(file)
                json_data['inputs']['user_input']['guest_voice_file'] = file_path
                logger.info(f"Saved guest voice file to {file_path}")
                
    elif content_type.startswith('application/json'):
        json_data = await request.json()
        
        if 'inputs' in json_data and 'user_input' in json_data['inputs']:
            user_input = json_data['inputs']['user_input']
            
            if 'host_voice_file' in user_input and user_input['host_voice_file']:
                if isinstance(user_input['host_voice_file'], str) and (
                    user_input['host_voice_file'].startswith('data:') or 
                    len(user_input['host_voice_file']) > 100  
                ):
                    file_path = await save_base64_file(user_input['host_voice_file'])
                    user_input['host_voice_file'] = file_path
                    logger.info(f"Saved host voice file from base64 to {file_path}")
            
            if 'guest_voice_file' in user_input and user_input['guest_voice_file']:
                if isinstance(user_input['guest_voice_file'], str) and (
                    user_input['guest_voice_file'].startswith('data:') or 
                    len(user_input['guest_voice_file']) > 100  
                ):
                    file_path = await save_base64_file(user_input['guest_voice_file'])
                    user_input['guest_voice_file'] = file_path
                    logger.info(f"Saved guest voice file from base64 to {file_path}")
    
    else:
        raise HTTPException(
            status_code=415, 
            detail=f"Unsupported media type: {content_type}. Use 'multipart/form-data' or 'application/json'."
        )
    
    try:
        payload = RequestPayload(**json_data)
        if hasattr(payload, 'execution_id'):
            request.state.execution_id = payload.execution_id
    except ValidationError as e:
        await cleanup_files(json_data)
        if 'execution_id' in json_data:
            request.state.execution_id = json_data['execution_id']
        raise HTTPException(status_code=422, detail=f"Validation error: {str(e)}")
    
    try:
        response = await process_podcast_request(payload)
        return response
    except Exception as e:
        await cleanup_files(json_data)
        logger.error(f"Error processing podcast request: {str(e)}", exc_info=True)
        return ResponsePayload(
            execution_id=payload.execution_id,
            status="error",
            message=f"Failed to process request: {str(e)}",
            results=[]
        )

@app.get("/health", status_code=200)
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@app.get("/")
async def root():
    return {"message": "Welcome to the GenAI Podcast Generator Agent API!"}

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    execution_id = getattr(request.state, "execution_id", str(uuid.uuid4()))
    logger.error(f"HTTP exception: {exc.detail} (status: {exc.status_code}, execution_id: {execution_id})")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "execution_id": execution_id,
            "status": "error",
            "message": exc.detail,
            "results": []
        },
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    execution_id = getattr(request.state, "execution_id", str(uuid.uuid4()))
    logger.error(f"Unhandled exception: {str(exc)} (execution_id: {execution_id})", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "execution_id": execution_id,
            "status": "error",
            "message": "Internal server error",
            "results": []
        },
    )
    
@app.middleware("http")
async def extract_execution_id(request: Request, call_next):
    try:
        content_type = request.headers.get('Content-Type', '')
        
        if content_type.startswith('application/json'):
            body = await request.body()
            if body:
                json_data = json.loads(body)
                if 'execution_id' in json_data:
                    request.state.execution_id = json_data['execution_id']
                    await request._receive()
        
        elif content_type.startswith('multipart/form-data'):
            pass
        
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Error in execution_id middleware: {str(e)}")
        return await call_next(request)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)