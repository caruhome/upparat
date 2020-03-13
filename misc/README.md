## Upparat Job Creator

A little helper to create an Upparat job.

### Usage

    ./upparat_create_job.py -h
    usage: upparat_create_job.py [-h] --file FILE --version VERSION --s3-bucket
                                 S3_BUCKET --arn-s3-role ARN_S3_ROLE --arn-iot
                                 ARN_IOT [--job-id JOB_ID] [--thing THING]
                                 [--group GROUP] [--force] [--dry-run]
                                 [--create-legacy-job]
                                 [--target-selection {SNAPSHOT,CONTINUOUS}]

    Create Upparat Jobs.

    --file FILE                 Filename that should be downloaded (S3 object key).
    --version VERSION           Version of the update bundle provided by --file.
    --s3-bucket S3_BUCKET       S3 Bucket name where the provided --file is stored.
    --arn-s3-role ARN_S3_ROLE   ARN of the S3 role that is used for the presignedUrlConfig.
    --arn-iot ARN_IOT           ARN of the IoT Core (where things and groups live).
    --job-id JOB_ID             A unique job id (if not provided, a generated UUID4).
    --thing THING               Thing(s) that should be updated. Or: cat things | ./upparat_create_job.py
    --group GROUP               Group(s) that should be included in this job.
    --force                     Force the update (ignore hooks).
    --dry-run                   Dry run / simulate what would happen.
    --create-legacy-job         Legacy flag for Upparat versions <1.5 where the force flag was a string.
    --target-selection          Change targetSelection of job.{SNAPSHOT,CONTINUOUS}

### Examples

    ./upparat_create_job.py \
    --file update-1-2.bin \
    --version 1.2 \
    --s3-bucket mybucket \
    --arn-s3-role arn:aws:iam::42424228359:role/iot_jobs_s3 \
    --arn-iot arn:aws:iot:eu-central-1:42424228359 \
    --job-id "My group and thing rollout to 1.2" \
    --group mygroup \
    --thing mything

*Output:*

    Running Upparat Job Creator \o/

    Going to create the following Upparat job:
     → Job: my-group-and-thing-rollout-to-1.2
     → File: https://mybucket.s3.amazonaws.com/update-1-2.bin
     → Version: 1.2
     → Force: False
     → ARN S3 role: arn:aws:iam::42424228359:role/iot_jobs_s3
     → ARN IoT: arn:aws:iot:eu-central-1:42424228359
     → Things: ['mything']
     → Groups: ['mygroup']

    ✓ Job 'my-group-and-thing-rollout-to-1.2' created!

*You can also pipe a list into `./upparat_create_job.py` with things:*

    cat things | ./upparat_create_job.py (...)

### Requirements

- Signed in AWS CLI
- boto3 (`pip install boto3`)
