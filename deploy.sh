#!/bin/bash

# Source AWS credentials
if [ -f "aws_config.sh" ]; then
    source aws_config.sh
else
    echo "Error: aws_config.sh not found. Please create this file with your AWS credentials."
    exit 1
fi

# Verify AWS credentials are set
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "Error: AWS credentials not set. Please check aws_config.sh"
    exit 1
fi

# Configuration
FUNCTION_NAME="finnhub-stock-data"
REGION=${AWS_DEFAULT_REGION:-"us-east-1"}  # Use configured region or default to us-east-1
ROLE_NAME="lambda-finnhub-role"
S3_BUCKET="finnhub-stock-data"  # Replace with your bucket name
SCHEDULE_RULE_NAME="finnhub-data-schedule"
SCHEDULE_EXPRESSION="rate(1 hour)"  # Run every hour, can be changed to other intervals

# Verify AWS CLI is installed and configured
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed. Please install it first."
    exit 1
fi

# Test AWS credentials
echo "Testing AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "Error: Invalid AWS credentials. Please check your aws_config.sh file."
    exit 1
fi

# Create IAM role for Lambda
echo "Creating IAM role..."
aws iam create-role \
    --role-name $ROLE_NAME \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }' \
    --region $REGION

# Attach basic Lambda execution policy
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
    --region $REGION

# Create and attach S3 policy
echo "Creating S3 policy..."
aws iam put-role-policy \
    --role-name $ROLE_NAME \
    --policy-name S3AccessPolicy \
    --policy-document "{
        \"Version\": \"2012-10-17\",
        \"Statement\": [
            {
                \"Effect\": \"Allow\",
                \"Action\": [
                    \"s3:PutObject\",
                    \"s3:GetObject\",
                    \"s3:ListBucket\"
                ],
                \"Resource\": [
                    \"arn:aws:s3:::${S3_BUCKET}\",
                    \"arn:aws:s3:::${S3_BUCKET}/*\"
                ]
            }
        ]
    }" \
    --region $REGION

# Get the role ARN
ROLE_ARN=$(aws iam get-role --role-name $ROLE_NAME --query 'Role.Arn' --output text)

# Create a temporary directory for packaging
PACKAGE_DIR="deployment_package"
mkdir -p $PACKAGE_DIR

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -t $PACKAGE_DIR/

# Copy the Lambda function and environment file
echo "Copying function files..."
cp lambda_function.py $PACKAGE_DIR/
cp .env $PACKAGE_DIR/

# Create the deployment package
echo "Creating deployment package..."
cd $PACKAGE_DIR
zip -r ../deployment.zip .
cd ..

# Deploy to AWS Lambda
echo "Deploying to AWS Lambda..."
aws lambda create-function \
    --function-name $FUNCTION_NAME \
    --runtime python3.9 \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://deployment.zip \
    --role $ROLE_ARN \
    --region $REGION \
    --timeout 30 \
    --memory-size 128 \
    --environment Variables={FINNHUB_API_KEY=$(grep FINNHUB_API_KEY .env | cut -d '=' -f2)}

# Create EventBridge rule
echo "Creating EventBridge rule..."
aws events put-rule \
    --name $SCHEDULE_RULE_NAME \
    --schedule-expression "$SCHEDULE_EXPRESSION" \
    --region $REGION

# Add permission for EventBridge to invoke Lambda
echo "Adding EventBridge permission to invoke Lambda..."
aws lambda add-permission \
    --function-name $FUNCTION_NAME \
    --statement-id "EventBridgeInvoke" \
    --action "lambda:InvokeFunction" \
    --principal "events.amazonaws.com" \
    --source-arn "arn:aws:events:$REGION:$(aws sts get-caller-identity --query Account --output text):rule/$SCHEDULE_RULE_NAME" \
    --region $REGION

# Create EventBridge target
echo "Creating EventBridge target..."
aws events put-targets \
    --rule $SCHEDULE_RULE_NAME \
    --targets "Id=1,Arn=arn:aws:lambda:$REGION:$(aws sts get-caller-identity --query Account --output text):function:$FUNCTION_NAME" \
    --region $REGION

# Clean up
echo "Cleaning up..."
rm -rf $PACKAGE_DIR
rm deployment.zip

echo "Deployment complete! Lambda function will run $SCHEDULE_EXPRESSION" 