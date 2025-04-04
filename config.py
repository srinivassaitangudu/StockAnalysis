import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# AWS Configuration
AWS_CONFIG = {
    'region_name': os.getenv('AWS_DEFAULT_REGION', 'us-east-1'),
    'aws_access_key_id': os.getenv('AWS_ACCESS_KEY_ID'),
    'aws_secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
}

# Lambda Configuration
LAMBDA_CONFIG = {
    'function_name': 'finnhub-stock-data',
    'role_name': 'lambda-finnhub-role',
    'runtime': 'python3.9',
    'handler': 'lambda_function.lambda_handler',
    'timeout': 30,
    'memory_size': 128,
}

# S3 Configuration
S3_CONFIG = {
    'bucket_name': 'finnhub-stock-data',
}

# EventBridge Configuration
EVENTBRIDGE_CONFIG = {
    'rule_name': 'finnhub-data-schedule',
    'schedule_expression': 'rate(1 hour)',
} 