# AWSChinaCreateAccount
This repo is to create and deploy account in China region without Control Tower

## Pre-requisites
- Ensure you have your AWS organization management account access permission
- You are familiar with CloudFormation
- You have installed AWS CLI
- Set management account profile

## Install
This create account toolkits should be installed in AWS organization management(master) account. 
### Preparation
Before running CloudFormation Stack, you need to upload lambda function zip file to specific S3 bucket. Here, I create a new S3 bucket to host these lambda zip file. You can also use your existing S3 bucket.

- Create an S3 bucket
```bash
aws s3api create-bucket --bucket $YOUR_LAMBDA_ZIP_BUCKET_NAME --region cn-north-1 --create-bucket-configuration LocationConstraint=cn-north-1 --profile $Your_Profile
```
- Enable Block Public Access
```
aws s3api put-public-access-block \
    --bucket $YOUR_LAMBDA_ZIP_BUCKET_NAME \
    --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
    --profile $Your_Profile
```
- Enable SSE Encrption
```
aws s3api put-bucket-encryption \
    --bucket $YOUR_LAMBDA_ZIP_BUCKET_NAME \
    --server-side-encryption-configuration '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}' \
    --profile $Your_Profile
```
- Enable Versioning
```
aws s3api put-bucket-versioning --bucket $YOUR_LAMBDA_ZIP_BUCKET_NAME --versioning-configuration Status=Enabled --profile $Your_Profile
```
- Upload Lambda Function Zip File
```
aws s3api put-object --bucket $YOUR_LAMBDA_ZIP_BUCKET_NAME --key lambda_create_account.zip --body lambda_create_account.zip --server-side-encryption AES256 --profile $Your_Profile
aws s3api put-object --bucket $YOUR_LAMBDA_ZIP_BUCKET_NAME --key lambda_deploy_account.zip --body lambda_deploy_account.zip --server-side-encryption AES256 --profile $Your_Profile
```
### Install Toolkits
- Define CloudFormation input parameters.Open parameters.json, define at least below parameters

| Key  |  Comments |
|---   |---        |
|InitialS3BucketName|The S3 bucket that hosts your bootstrap cfn template. This template will be deployed to new created account|
|ToolInstallS3Bucket|YOUR_LAMBDA_ZIP_BUCKET_NAME, the bucket that hosts lambda functions zip file|
|SAMLMetadataS3BucketName|The S3 bucket that hosts your IAM SAML federation metadata xml file, which will be shared to all memeber account|

- Use CloudFormation to deploy account creation toolkits.
```
aws cloudformation create-stack --stack-name account-provision-toolkit --template-body file://AccountCreationToolkitInstall.yml --parameters file://parameters.json --capabilities CAPABILITY_NAMED_IAM --region=cn-north-1 --profile $Your_Profile
```
- Upload your bootstrip template to "InitialS3BucketName" bucket. In this repo is a template AccountInitial.yml. Please remove the content and define your own resources you want to deploy into new account.
``` 
aws s3api put-object --bucket $InitialS3BucketName --key AccountInitial.yml --body AccountInitial.yml --server-side-encryption AES256 --profile $Your_Profile
```
- If you have SAML federation, you need to update your SAML metadata file to $SAMLMetadataS3BucketName as well

## Usage
Now you can trigger Step Functions state machine to start creating accounts
```
aws stepfunctions start-execution \
  --state-machine-arn arn:aws-cn:states:cn-north-1:$YOUR_MANAGEMENT_ACCOUNT_ID:stateMachine:AccountInitialStateMachine \
  --input "{\"account_name\": \"$ACCOUNT_NAME\", \"account_email\": \"$ACCOUNT_EMAIL\", \"ou_name\": \"$OU_NAME\"}" \
  --profile $Your_Profile \
  --region cn-north-1
```

## Contact
If you want to contact me you can reach me at
[@Jimmie Chen](54409352@qq.com) 📖