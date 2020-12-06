
'''
AWS Organizations Create New Accounts in China Region.

This module creates a new account using Organizations.

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
    ou_name = event.get('ou_name')
    scp = event.get('scp')

    access_to_billing = os.environ['access_to_billing']
    account_role = os.environ['account_role']
    metadata_bucket_name = os.environ['metadata_bucket_name']

    # create account
    print("Creating new account: " + account_name + " (" + account_email + ")")
    account_create_response = create_account(account_name, account_email, account_role, access_to_billing, ou_name, scp)
    account_id = account_create_response.get('account_id')
    ou_name = account_create_response.get('ou_name')
    # Comment the above line and uncomment the below line to skip account creation and just test follow script (for testing)
    # account_id = "123456789012"
    print("Created acount: " + account_id)
    # update account inventory DDB table
    add_DDB_status = addAccountInfoToDDBTable(account_name, account_id, account_email, ou_name)
    print (add_DDB_status)
    # Update SAML Metadata bucket policy
    updateSAMLMetadataBucketPolicy(account_id, metadata_bucket_name)
    print (account_id + "added to " + metadata_bucket_name + " bucket policy condition.")

    return {
        'statusCode': 200,
        'body': json.dumps('Success!'),        
        'account_id': account_id,
        'ou_name': ou_name
    }


def create_account(
        account_name,
        account_email,
        account_role='OrganizationAccountAccessRole',
        access_to_billing='DENY',
        ou_name=None,
        scp=None):

    '''
        Create a new AWS account and add it to an organization
    '''

    client = boto3.client('organizations')
    try:
        create_account_response = client.create_account(Email=account_email, AccountName=account_name,
                                                        RoleName=account_role,
                                                        IamUserAccessToBilling=access_to_billing)
    except botocore.exceptions.ClientError as e:
        print(e)
        sys.exit(1)

    time.sleep(10)

    account_status = 'IN_PROGRESS'
    while account_status == 'IN_PROGRESS':
        create_account_status_response = client.describe_create_account_status(
            CreateAccountRequestId=create_account_response.get('CreateAccountStatus').get('Id'))
        print("Create account status "+str(create_account_status_response))
        account_status = create_account_status_response.get('CreateAccountStatus').get('State')
        time.sleep(10)
    if account_status == 'SUCCEEDED':
        account_id = create_account_status_response.get('CreateAccountStatus').get('AccountId')
    elif account_status == 'FAILED':
        print("Account creation failed: " + create_account_status_response.get('CreateAccountStatus').get('FailureReason'))
        sys.exit(1)

    root_id = client.list_roots().get('Roots')[0].get('Id')

    organization_unit_id = None

    ou_response = client.list_organizational_units_for_parent(
        ParentId=root_id
    )
    if ou_name is not None:
        for ou in ou_response['OrganizationalUnits']:
            if ou['Name'] == ou_name:
                organization_unit_id = ou['Id']

        try:
            move_account_response = client.move_account(AccountId=account_id, SourceParentId=root_id,
                                                        DestinationParentId=organization_unit_id)
            print ('move success')
            print (move_account_response)
        except Exception as ex:
            template = "An exception of type {0} occurred. Arguments:\n{1!r} "
            message = template.format(type(ex).__name__, ex.args)
            ou_name = 'Root'
            print('move failed')
            print('ou name not found under organizaiton root')
            print(message)
    else:
        ou_name = 'Root'
        print('No OU name defined')


    # Attach policy to account if exists, Only useful in Global region
    if scp is not None:
        attach_policy_response = client.attach_policy(PolicyId=scp, TargetId=account_id)
        print("Attach policy response "+str(attach_policy_response))

    return {
        'statusCode': 200,
        'account_id': account_id,        
        'ou_name': ou_name
    }

def updateSAMLMetadataBucketPolicy(new_account, bucket_name):
    '''
        This is a workaround solution for the limitation of condition aws:PrincipalOrgID as of writing this script.
        Update SAML Metadata XML bucket policy. Add the new created account ID to condition aws:PrincipalAccount
    '''
    client = boto3.client('s3')
    print ("Adding account ID " + new_account + " to " + bucket_name + "bucket policy condition")
    get_response = client.get_bucket_policy(
        Bucket = bucket_name
    )

    current_policy = get_response['Policy']
    current_policy_dict = json.loads(current_policy)

    for statement in current_policy_dict['Statement']:
        if statement['Sid'] == 'RestrictAccountID':
            try:
                if isinstance(statement['Condition']['StringEquals']['aws:PrincipalAccount'], list):
                    statement['Condition']['StringEquals']['aws:PrincipalAccount'].append(new_account)
                else:
                    statement['Condition']['StringEquals']['aws:PrincipalAccount'] = [statement['Condition']['StringEquals']['aws:PrincipalAccount'], new_account]
            except botocore.exceptions.ClientError as e:
                print(e)
                sys.exit(1)
        else:
            continue

    new_policy = json.dumps(current_policy_dict)

    put_response = client.put_bucket_policy(
        Bucket = bucket_name,
        ConfirmRemoveSelfBucketAccess = True,
        Policy = new_policy
    )
    return put_response

def addAccountInfoToDDBTable(account_name, account_id, account_email, ou_name):
    '''
        Add new created account information to DynamoDB tables as an account inventory.
    '''
    client = boto3.client('dynamodb')
    print ("Adding account " + account_name + " to lz_account_inventory DynamoDB table")
    response = client.put_item(
        TableName='lz_account_inventory',
        Item={
            'account_name': {
                'S': account_name,
            },
            'account_id': {
                'S': account_id,
            },
            'account_email': {
                'S': account_email,
            },
            'ou_name': {
                'S': ou_name,
            },
        },
        ConditionExpression='attribute_not_exists(account_name)',
        ReturnConsumedCapacity='TOTAL',
    )

    print(response)