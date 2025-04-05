# AWS Lambda Finnhub Stock Data Fetcher

This project sets up an AWS Lambda function that fetches stock data from Finnhub API and stores it in S3.

## Setup

1. Install the required packages:
```bash
pip install -r requirements.txt
```

2. Set up your AWS and Finnhub credentials:
```bash
python setup_credentials.py
```

3. Test your credentials:
```bash
python test_credentials.py
```

4. Deploy the Lambda function:
```bash
python deploy.py
```

## Configuration

You can modify the configuration in `config.py`:

- AWS region
- Lambda function settings
- S3 bucket name
- EventBridge schedule

## Troubleshooting

### "Unable to locate credentials" error

If you encounter this error, make sure:

1. You've run `setup_credentials.py` and entered your AWS credentials
2. Your `.env` file contains valid AWS credentials
3. You've run `test_credentials.py` to verify your credentials work

### Other common issues

- **S3 bucket doesn't exist**: Create the S3 bucket specified in `config.py`
- **IAM permissions**: Make sure your AWS user has permissions to create Lambda functions, IAM roles, and EventBridge rules
- **Region issues**: Make sure the region in your credentials matches the region in `config.py`

## Project Structure

- `deploy.py`: Main deployment script
- `lambda_function.py`: Lambda function code
- `config.py`: Configuration settings
- `setup_credentials.py`: Helper script to set up credentials
- `test_credentials.py`: Helper script to test credentials
- `.env`: Contains your AWS and Finnhub credentials (not in git)
- `requirements.txt`: Python dependencies 