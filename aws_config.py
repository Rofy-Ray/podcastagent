import boto3
from botocore.config import Config
import os
import logging
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def configure_s3():
    """
    Configure S3 client with credentials from environment variables
    """
    required_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"Missing AWS environment variables: {', '.join(missing_vars)}")
        logger.warning("S3 uploads may fail without proper credentials")
    
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION')
    )
    
async def generate_presigned_url(bucket_name, object_key, expiration=3600):
    """
    Generate a presigned URL for an S3 object
    
    Args:
        bucket_name (str): The S3 bucket name
        object_key (str): The S3 object key
        expiration (int): Expiration time in seconds
        
    Returns:
        str: Presigned URL
    """
    s3_client = await configure_s3()
    
    presigned_url = s3_client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': bucket_name,
            'Key': object_key
        },
        ExpiresIn=expiration
    )
    
    return presigned_url
    
async def upload_to_s3(file_path, bucket_name, object_key, expiration=3600):
    """
    Upload a file to S3 and return a presigned URL
    
    Args:
        file_path (str): Path to the file to upload
        bucket_name (str): The S3 bucket name
        object_key (str): The S3 object key
        expiration (int): Expiration time in seconds
        
    Returns:
        str: Presigned URL for the uploaded object
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if object_key is None:
        object_key = os.path.basename(file_path)
        
    s3_client = await configure_s3()
    
    try:
        s3_client.upload_file(file_path, bucket_name, object_key)
        # logger.info(f"Successfully uploaded file to s3://{bucket_name}/{object_key}")
    except Exception as e:
        logger.error(f"Failed to upload file to S3: {str(e)}")
        raise e
    
    return await generate_presigned_url(bucket_name, object_key, expiration)