const { S3Client, PutBucketAclCommand } = require('@aws-sdk/client-s3');

const client = new S3Client({});

async function keepPrivate(bucket) {
  await client.send(new PutBucketAclCommand({
    Bucket: bucket,
    ACL: 'private',
  }));
}

module.exports = { keepPrivate };
