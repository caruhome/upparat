#!/usr/bin/env python3
import argparse
import json
import sys
from uuid import uuid4

import boto3

iot_client = boto3.client("iot")


def parse_arguments(args):
    parser = argparse.ArgumentParser(description="Create Upparat Jobs.")
    parser.add_argument(
        "--file",
        required=True,
        help="Filename that should be downloaded (S3 object key).",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Version of the update bundle provided by --file.",
    )
    parser.add_argument(
        "--s3-bucket",
        required=True,
        help="S3 Bucket name where the provided --file is stored.",
    )
    parser.add_argument(
        "--arn-s3-role",
        required=True,
        help="ARN of the S3 role that is used for the presignedUrlConfig.",
    )
    parser.add_argument(
        "--arn-iot",
        required=True,
        help="ARN of the IoT Core (where things and groups live).",
    )
    parser.add_argument(
        "--job-id",
        default=str(uuid4()),
        help="A unique job id (if not provided, a generated UUID4).",
    )
    parser.add_argument(
        "--thing",
        action="append",
        default=[],
        help="Thing(s) that should be updated. Or: cat things | ./upparat_create_job.py",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="Group(s) that should be included in this job.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force the update (ignore version & pre-download hooks).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Dry run / simulate what would happen.",
    )
    parser.add_argument(
        "--target-selection",
        choices=["SNAPSHOT", "CONTINUOUS"],
        default="SNAPSHOT",
        help="Change targetSelection of job.",
    )

    return parser.parse_args(args)


def create_job_document(s3_object_url, version, force):
    return json.dumps(
        {
            "action": "upparat-update",
            "file": f"${{aws:iot:s3-presigned-url:{s3_object_url}}}",
            "version": version,
            "force": force,
        }
    )


def create_job(job_id, document, targets, arn_s3_role, target_selection):
    try:
        iot_client.create_job(
            jobId=job_id,
            document=document,
            targets=targets,
            targetSelection=target_selection,
            presignedUrlConfig={"roleArn": arn_s3_role},
        )
    except Exception as e:
        print(f"✗ Job '{job_id}' not created!")
        print(f" → Reason: {e}")
        sys.exit(1)

    print(f"✓ Created job '{job_id}'.")


def build_targets(arn_iot, thing_argument, group_argument):
    """
    Support piping a list of things to this tool:
        cat things.txt | ./upparat_create_job.py
    or:
        ./upparat_create_job.py --thing thing1 --thing thingN
    or for groups:
        ./upparat_create_job.py --group group1 --group groupN

    """
    things = set(thing_argument)
    groups = set(group_argument)

    if not sys.stdin.isatty():
        for line in sys.stdin.readlines():
            thing = line.rstrip()
            if thing:
                things.add(thing)

    if not things and not groups:
        print("✗ No things or groups defined. Exiting.")
        sys.exit()

    target_arns = []
    target_arns += [f"{arn_iot}:thing/{thing}" for thing in things]
    target_arns += [f"{arn_iot}:thinggroup/{group}" for group in groups]

    return target_arns, list(things), list(groups)


def main(arguments):
    print("Running Upparat Job Creator \\o/\n")
    job_id = arguments.job_id.replace(" ", "-").lower()

    target_arns, thing_names, group_names = build_targets(
        arguments.arn_iot, arguments.thing, arguments.group
    )

    s3_object_url = f"https://{arguments.s3_bucket}.s3.amazonaws.com/{arguments.file}"

    force = arguments.force

    document = create_job_document(
        s3_object_url=s3_object_url, version=arguments.version, force=force
    )

    print("Going to create the following Upparat job:")
    print(f" → Job: {job_id}")
    print(f" → File: {s3_object_url}")
    print(f" → Version: {arguments.version}")
    print(f" → Force: {force}")
    print(f" → ARN S3 role: {arguments.arn_s3_role}")
    print(f" → ARN IoT: {arguments.arn_iot}")
    print(f" → Things: {thing_names}")
    print(f" → Groups: {group_names}\n")
    print(f"AWS IoT Job Document:\n")
    print(json.dumps(json.loads(document), indent=2))
    print("")

    if not arguments.dry_run:
        create_job(
            job_id=job_id,
            document=document,
            targets=target_arns,
            arn_s3_role=arguments.arn_s3_role,
            target_selection=arguments.target_selection,
        )
    else:
        print(
            f"✓ Would have created job '{job_id}'. (remove --dry-run to create it for real)"
        )


if __name__ == "__main__":
    main(parse_arguments(sys.argv[1:]))
