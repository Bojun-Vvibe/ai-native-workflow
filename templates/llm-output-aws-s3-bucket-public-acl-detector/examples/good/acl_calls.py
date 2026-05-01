import boto3

s3 = boto3.client("s3")


def keep_private():
    s3.put_bucket_acl(Bucket="reports", ACL="private")


def upload_with_owner_only(key):
    s3.put_object_acl(Bucket="reports", Key=key, ACL="bucket-owner-full-control")


def init_bucket():
    s3.create_bucket(Bucket="brand-new", ACL="private")
