import os
import json
import boto3
import zipfile
import tempfile
import shutil
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from config import AWS_CONFIG, LAMBDA_CONFIG, S3_CONFIG, EVENTBRIDGE_CONFIG

class LambdaDeployer:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Configuration
        self.function_name = LAMBDA_CONFIG['function_name']
        self.role_name = LAMBDA_CONFIG['role_name']
        self.s3_bucket = S3_CONFIG['bucket_name']
        self.schedule_rule_name = EVENTBRIDGE_CONFIG['rule_name']
        self.schedule_expression = EVENTBRIDGE_CONFIG['schedule_expression']
        
        # Initialize AWS clients with explicit credentials
        self.session = boto3.Session(
            aws_access_key_id=AWS_CONFIG['aws_access_key_id'],
            aws_secret_access_key=AWS_CONFIG['aws_secret_access_key'],
            region_name=AWS_CONFIG['region_name']
        )
        
        self.lambda_client = self.session.client('lambda')
        self.iam = self.session.client('iam')
        self.events = self.session.client('events')
        self.sts = self.session.client('sts')
        self.s3 = self.session.client('s3')
        
        # Get account ID
        self.account_id = self.sts.get_caller_identity()["Account"]
        
    def create_zip_package(self):
        """Create deployment package"""
        print("Creating deployment package...")
        
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp()
        zip_path = "deployment.zip"
        
        try:
            # Install dependencies
            os.system(f'pip install -r requirements.txt -t {temp_dir}')
            
            # Copy function file
            shutil.copy2('lambda_function.py', temp_dir)
            shutil.copy2('.env', temp_dir)
            
            # Create zip file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, arcname)
                        
            return zip_path
            
        finally:
            # Clean up temporary directory
            shutil.rmtree(temp_dir)
            
    def create_or_update_role(self):
        """Create or update IAM role"""
        print("Setting up IAM role...")
        
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }]
        }
        
        try:
            # Try to create role
            response = self.iam.create_role(
                RoleName=self.role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy)
            )
            print("Created new IAM role")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                print("IAM role already exists")
                response = self.iam.get_role(RoleName=self.role_name)
            else:
                raise
                
        # Attach policies
        self.iam.attach_role_policy(
            RoleName=self.role_name,
            PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        )
        
        # Create S3 policy
        s3_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    f"arn:aws:s3:::{self.s3_bucket}",
                    f"arn:aws:s3:::{self.s3_bucket}/*"
                ]
            }]
        }
        
        self.iam.put_role_policy(
            RoleName=self.role_name,
            PolicyName='S3AccessPolicy',
            PolicyDocument=json.dumps(s3_policy)
        )
        
        return response['Role']['Arn']
        
    def deploy_lambda(self, role_arn, zip_path):
        """Deploy or update Lambda function"""
        with open(zip_path, 'rb') as zip_file:
            zip_bytes = zip_file.read()
            
        try:
            # Try to get function (will raise exception if it doesn't exist)
            self.lambda_client.get_function(FunctionName=self.function_name)
            
            print("Updating existing Lambda function...")
            # Update function code
            self.lambda_client.update_function_code(
                FunctionName=self.function_name,
                ZipFile=zip_bytes
            )
            
            # Update function configuration
            self.lambda_client.update_function_configuration(
                FunctionName=self.function_name,
                Runtime=LAMBDA_CONFIG['runtime'],
                Handler=LAMBDA_CONFIG['handler'],
                Role=role_arn,
                Timeout=LAMBDA_CONFIG['timeout'],
                MemorySize=LAMBDA_CONFIG['memory_size'],
                Environment={
                    'Variables': {
                        'FINNHUB_API_KEY': os.getenv('FINNHUB_API_KEY')
                    }
                }
            )
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print("Creating new Lambda function...")
                self.lambda_client.create_function(
                    FunctionName=self.function_name,
                    Runtime=LAMBDA_CONFIG['runtime'],
                    Handler=LAMBDA_CONFIG['handler'],
                    Role=role_arn,
                    Code={'ZipFile': zip_bytes},
                    Timeout=LAMBDA_CONFIG['timeout'],
                    MemorySize=LAMBDA_CONFIG['memory_size'],
                    Environment={
                        'Variables': {
                            'FINNHUB_API_KEY': os.getenv('FINNHUB_API_KEY')
                        }
                    }
                )
            else:
                raise
                
    def setup_eventbridge(self):
        """Set up EventBridge rule"""
        print("Setting up EventBridge rule...")
        
        # Create or update rule
        self.events.put_rule(
            Name=self.schedule_rule_name,
            ScheduleExpression=self.schedule_expression
        )
        
        # Add Lambda permission
        try:
            self.lambda_client.add_permission(
                FunctionName=self.function_name,
                StatementId='EventBridgeInvoke',
                Action='lambda:InvokeFunction',
                Principal='events.amazonaws.com',
                SourceArn=f'arn:aws:events:{AWS_CONFIG["region_name"]}:{self.account_id}:rule/{self.schedule_rule_name}'
            )
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceConflictException':
                raise
                
        # Update EventBridge target
        self.events.put_targets(
            Rule=self.schedule_rule_name,
            Targets=[{
                'Id': '1',
                'Arn': f'arn:aws:lambda:{AWS_CONFIG["region_name"]}:{self.account_id}:function:{self.function_name}'
            }]
        )
        
    def create_s3_bucket(self):
        """Create S3 bucket if it doesn't exist"""
        print("Setting up S3 bucket...")
        try:
            # Check if bucket exists
            self.s3.head_bucket(Bucket=self.s3_bucket)
            print(f"S3 bucket '{self.s3_bucket}' already exists")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket doesn't exist, create it
                print(f"Creating S3 bucket '{self.s3_bucket}'...")
                self.s3.create_bucket(
                    Bucket=self.s3_bucket,
                    CreateBucketConfiguration={
                        'LocationConstraint': AWS_CONFIG['region_name']
                    }
                )
                print(f"S3 bucket '{self.s3_bucket}' created successfully")
            else:
                raise

    def deploy(self):
        """Main deployment process"""
        try:
            print("Starting deployment process...")
            
            # Create S3 bucket first
            self.create_s3_bucket()
            
            # Create deployment package
            zip_path = self.create_zip_package()
            
            # Setup IAM role
            role_arn = self.create_or_update_role()
            
            # Wait for role to be ready (IAM propagation)
            print("Waiting for IAM role to be ready...")
            import time
            time.sleep(10)
            
            # Deploy Lambda function
            self.deploy_lambda(role_arn, zip_path)
            
            # Setup EventBridge
            self.setup_eventbridge()
            
            print(f"Deployment complete! Lambda function will run {self.schedule_expression}")
            
        except Exception as e:
            print(f"Deployment failed: {str(e)}")
            raise
            
        finally:
            # Clean up
            if os.path.exists('deployment.zip'):
                os.remove('deployment.zip')
                
if __name__ == '__main__':
    deployer = LambdaDeployer()
    deployer.deploy() 