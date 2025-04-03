import os
import json
import requests
import boto3
import logging
from datetime import datetime
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Load environment variables
load_dotenv()

# Get Finnhub API key from environment variables
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
FINNHUB_BASE_URL = 'https://finnhub.io/api/v1'

# Initialize S3 client
s3 = boto3.client('s3')
S3_BUCKET = 'finnhub-stock-data'  # Replace with your bucket name

def store_in_s3(data, symbol, timestamp):
    """Store the data in S3 with a timestamp-based key"""
    try:
        key = f"{symbol}/{timestamp.year}/{timestamp.month}/{timestamp.day}/{timestamp.hour}/{timestamp.isoformat()}.json"
        
        # Check if bucket exists
        try:
            s3.head_bucket(Bucket=S3_BUCKET)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.error(f"S3 bucket {S3_BUCKET} does not exist")
                raise
            elif error_code == '403':
                logger.error(f"Access denied to S3 bucket {S3_BUCKET}")
                raise
        
        # Store the data
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(data),
            ContentType='application/json'
        )
        logger.info(f"Successfully stored data in S3: {key}")
        return key
    except ClientError as e:
        logger.error(f"Error storing data in S3: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error storing data in S3: {str(e)}")
        raise

def lambda_handler(event, context):
    try:
        # Extract symbol from the event or use default
        symbol = event.get('symbol', 'AAPL')  # Default to AAPL if no symbol provided
        current_time = datetime.utcnow()
        
        logger.info(f"Fetching data for symbol: {symbol}")
        
        # Make request to Finnhub API
        response = requests.get(
            f'{FINNHUB_BASE_URL}/quote',
            params={'symbol': symbol, 'token': FINNHUB_API_KEY}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Add metadata to the data
            data['metadata'] = {
                'symbol': symbol,
                'timestamp': current_time.isoformat(),
                'source': 'finnhub'
            }
            
            # Store in S3
            s3_key = store_in_s3(data, symbol, current_time)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Success',
                    'data': data,
                    's3_key': s3_key
                })
            }
        else:
            logger.error(f"Error from Finnhub API: {response.status_code} - {response.text}")
            return {
                'statusCode': response.status_code,
                'body': json.dumps({
                    'message': 'Error fetching data from Finnhub',
                    'error': response.text
                })
            }
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Internal server error',
                'error': str(e)
            })
        } 