

'''Provision Bootstrap Resources target account via CloudFormation

This module calls CloudFormation to deploy bootstrap resources in target account via a tempalte file in master account S3 Bucket.

'''

import json
import boto3
import botocore
import time
import sys
import argparse
import os


def lambda_handler(event, context):
    
    account_name = event['account_name']
    account_email = event['account_email']
    account_id = event['output']['account_id']
    ou_name = event['output']['ou_name']
    organization_unit_id = event.get('organization_unit_id')
    scp = event.get('scp')

    account_role = os.environ['account_role']
    stack_name = os.environ['stack_name']
    stack_region = os.environ['stack_region']
    bucket_name = os.environ['bucket_name']
    template_file = os.environ['template_file']
    metadata_bucket_name = os.environ['metadata_bucket_name']

    print("Getting credential")
    credentials = assume_role(account_id, account_role)

    print("Deploying resources from " + template_file + " in " + bucket_name + " as " + stack_name + " in " + stack_region)
    
    template = get_template(bucket_name, template_file)
    
    stack = deploy_resources(credentials, template, stack_name, stack_region)
    print("Resources deployed for account " + account_id + " (" + account_email + ")")

    change_alias_status = change_account_alias(credentials, account_name)
    print ("Account alias successfully changed!")

    return {
        'statusCode': 200,
        'status': 'Success',
        'account_name': account_name,
        'account_email': account_email,
        'account_id': account_id,
        'ou_name': ou_name,
        'stack_id': stack["Stacks"][0]["StackId"]
    }


def assume_role(account_id, account_role):

    '''
        Assume admin role within the newly created account and return credentials
    '''

    sts_client = boto3.client('sts')
    role_arn = 'arn:aws-cn:iam::' + account_id + ':role/' + account_role

    # assume_role 

    assuming_role = True
    while assuming_role is True:
        try:
            assuming_role = False
            assumedRoleObject = sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="NewAccountRole"
            )
        except botocore.exceptions.ClientError as e:
            assuming_role = True
            print(e)
            print("Retrying...")
            time.sleep(10)

    # get the temporary credentials
    return assumedRoleObject['Credentials']


def get_template(bucket_name, template_file):

    '''
        Read a template file from S3 bucket and return the contents
    '''

    print("Reading resources from " + template_file)
    s3_client = boto3.client('s3')
    s3_response = s3_client.get_object(
        Bucket=bucket_name,
        Key=template_file,
        )
    cf_template_bytes = s3_response['Body'].read()
    cf_template = str(cf_template_bytes, encoding = "utf8")
    return cf_template


def deploy_resources(credentials, template, stack_name, stack_region):

    '''
        Create a CloudFormation stack of resources within the new account
    '''

    datestamp = time.strftime("%d/%m/%Y")
    client = boto3.client('cloudformation',
                          aws_access_key_id=credentials['AccessKeyId'],
                          aws_secret_access_key=credentials['SecretAccessKey'],
                          aws_session_token=credentials['SessionToken'],
                          region_name=stack_region)
    print("Creating stack " + stack_name + " in " + stack_region)

    # Deploy stack in account. Error will be captured by StepFunction and start retry.
    create_stack_response = client.create_stack(
        StackName=stack_name,
        TemplateBody=template,
        NotificationARNs=[],
        Capabilities=[
            'CAPABILITY_NAMED_IAM',
        ],
        OnFailure='ROLLBACK',
        Tags=[
            {
                'Key': 'ManagedResource',
                'Value': 'True'
            },
            {
                'Key': 'DeployDate',
                'Value': datestamp
            },
            {
                'Key': 'isLandingZoneResource',
                'Value': 'True'
            }
        ]
    )

    stack_building = True
    print("Stack creation in process...")
    #print(create_stack_response)
    while stack_building is True:
        event_list = client.describe_stack_events(StackName=stack_name).get("StackEvents")
        stack_event = event_list[0]
        if (stack_event.get('ResourceType') == 'AWS::CloudFormation::Stack' and
           stack_event.get('ResourceStatus') == 'CREATE_COMPLETE'):
            stack_building = False
            print("Stack construction complete.")
        elif (stack_event.get('ResourceType') == 'AWS::CloudFormation::Stack' and
              stack_event.get('ResourceStatus') == 'ROLLBACK_COMPLETE'):
            stack_building = False
            print("Stack construction failed.")
            sys.exit(1)
        else:
            print(stack_event)
            print("Stack building . . .")
            time.sleep(15)
    
    stack = client.describe_stacks(StackName=stack_name)
    return stack
    
def change_account_alias(credentials, account_name):
    '''
        Change AWS account alias name.
    '''
    lower_account_name = account_name.lower()
    print ("Changing account alias to " + lower_account_name)

    iam_client = boto3.client('iam',
                            aws_access_key_id=credentials['AccessKeyId'],
                            aws_secret_access_key=credentials['SecretAccessKey'],
                            aws_session_token=credentials['SessionToken']
                            )
    response = iam_client.create_account_alias(
        AccountAlias = lower_account_name
        )
    return response
