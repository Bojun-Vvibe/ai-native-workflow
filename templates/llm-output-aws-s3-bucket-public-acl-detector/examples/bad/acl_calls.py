import boto3

s3 = boto3.client("s3")


def make_assets_public():
    s3.put_bucket_acl(
        Bucket="my-public-assets",
        ACL="public-read",
    )


def share_object(key):
    s3.put_object_acl(
        Bucket="reports",
        Key=key,
        ACL="public-read-write",
    )


def init_bucket():
    s3.create_bucket(
        Bucket="brand-new",
        ACL="authenticated-read",
    )
