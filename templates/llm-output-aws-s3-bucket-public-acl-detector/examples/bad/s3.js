const { S3Client, PutBucketAclCommand, PutBucketPolicyCommand } = require('@aws-sdk/client-s3');

const client = new S3Client({});

async function makePublic(bucket) {
  await client.send(new PutBucketAclCommand({
    Bucket: bucket,
    ACL: 'public-read',
  }));
}

async function applyOpenPolicy(bucket) {
  const policy = JSON.stringify({
    Version: '2012-10-17',
    Statement: [{
      Effect: 'Allow',
      Principal: '*',
      Action: 's3:GetObject',
      Resource: `arn:aws:s3:::${bucket}/*`,
    }],
  });
  await client.send(new PutBucketPolicyCommand({ Bucket: bucket, Policy: policy }));
}

module.exports = { makePublic, applyOpenPolicy };
