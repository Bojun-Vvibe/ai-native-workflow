package main

import (
	"context"

	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
)

func openBucket(ctx context.Context, client *s3.Client, name string) error {
	_, err := client.PutBucketAcl(ctx, &s3.PutBucketAclInput{
		Bucket: &name,
		ACL:    types.BucketCannedACLPublicReadWrite,
	})
	return err
}
