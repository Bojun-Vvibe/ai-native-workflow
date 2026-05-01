package com.example.s3;

import com.amazonaws.services.s3.AmazonS3;
import com.amazonaws.services.s3.model.CannedAccessControlList;
import com.amazonaws.services.s3.model.SetBucketAclRequest;

public class BucketAcl {
    public void open(AmazonS3 s3, String bucket) {
        SetBucketAclRequest req = new SetBucketAclRequest(bucket, CannedAccessControlList.PublicRead);
        s3.setBucketAcl(req);
    }
}
