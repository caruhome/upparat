import json
import os
from uuid import uuid4

import boto3

iot_client = boto3.client("iot")

ENV_THINGS = "THINGS"
ENV_S3_ROLE_ARN = "S3_ROLE_ARN"
ENV_S3_FILE_URL = "S3_FILE_URL"


def create_job(targets, s3_url, role_arn):
    job_id = str(uuid4())
    iot_client.create_job(
        jobId=job_id,
        targets=targets,
        presignedUrlConfig={"roleArn": role_arn, "expiresInSec": 3600},
        document=json.dumps(
            {
                "action": "update",
                # "meta": "same",
                # "force": True,
                "version": "0.1.3",
                "file": f"${{aws:iot:s3-presigned-url:{s3_url}}}",
            }
        ),
        targetSelection="SNAPSHOT",
        jobExecutionsRolloutConfig={"maximumPerMinute": 1},
    )

    print(f"Created job {job_id}")

    return job_id


if __name__ == "__main__":
    things = os.environ.get(ENV_THINGS, "").split(",")
    assert things

    s3_role_arn = os.environ.get(ENV_S3_ROLE_ARN)
    s3_file_url = os.environ.get(ENV_S3_FILE_URL)

    create_job(things, s3_file_url, s3_role_arn)
