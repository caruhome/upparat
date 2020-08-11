# Examples Setup

There are two slightly different examples:

1. `docker-compose run upparat-alpn`, directly connect to AWS from Upparat. This is probably what you want unless you have more than one MQTT client connected to AWS IoT.
1. `docker-compose run upparat-bridged`, connect to Mosquitto in bridged mode that is connected to AWS (advanced).

## AWS Setup

1. [Create an AWS IoT Thing](https://docs.aws.amazon.com/general/latest/gr/iot-core.html) and download the certificates. We will reference the downloaded files as:

```bash
.cert.pem → certfile
.private.key → keyfile

# https://www.amazontrust.com/repository/AmazonRootCA1.pem
AmazonRootCA1.pem.txt → cafile
```

2. Create and attach the following policy to the Thing's certificate:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": ["*"],
      "Resource": ["*"],
      "Effect": "Allow"
    }
  ]
}
```

3. Create an S3 bucket and upload a test file (i.e. your firmware file).
4. Create a role for the principle `IoT` and with the following policy attached:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::your-upparat-jobs-bucket/*"
    }
  ]
}
```

## Certificates

[Create device certifactes](https://docs.aws.amazon.com/general/latest/gr/iot-core.html).

Notes:

- Client Certificate, `--certificate-pem-outfile = certfile`

## Upparat via Mosquitto AWS Bridge

    THING_NAME=YOUR_THING_NAME
    BROKER=YOUR_BROKER_HOST

    cp mosquitto/aws-bridge.conf.tmpl mosquitto/aws-bridge.conf
    sed -i -e "s|@THING_NAME@|${THING_NAME}|g" mosquitto/aws-bridge.conf
    sed -i -e "s|@BROKER@|${BROKER}|g" mosquitto/aws-bridge.conf
    sed -i -e "s|@BASE_DIR@|${PWD}|g" mosquitto/aws-bridge.conf

Notes:

- `YOUR_THING_NAME`: [AWS Thing Name](https://docs.aws.amazon.com/iot/latest/developerguide/thing-registry.html)
- `BROKER`: [AWS Broker](https://docs.aws.amazon.com/general/latest/gr/iot-core.html)

Run example:

`docker-compose run upparat-bridged`

### Upparat

1.  Copy _[upparat/config.ini.tmpl](upparat/config.ini.tmpl)_ to _./config.ini_ and replace the `@DEVICE_ID@` placeholder:

        THING_NAME=YOUR_THING_NAME
        cp upparat/config.ini.tmpl upparat/config.ini
        sed -i -e "s|@THING_NAME@|${THING_NAME}|g" upparat/config.ini
        sed -i -e "s|@BASE_DIR@|${PWD}|g" upparat/config.ini

1.  Start upparat: `upparat -c upparat/config.ini`

### Test Jobs

To use AWS Iot jobs with pre-signed S3 URLs create a S3 bucket and a corresponding role.

#### AWS CloudFormation Setup

1. Install [AWS CLI](https://aws.amazon.com/cli/)
1. Deploy stack:
   ```bash
   aws cloudformation deploy --template-file upparat-test.yaml --capabilities CAPABILITY_IAM --stack-name upparat-test
   export UPPARAT_TEST_BUCKET_NAME=`aws cloudformation describe-stacks --stack-name  upparat-test --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text`
   export UPPARAT_TEST_ROLE_ARN=`aws cloudformation describe-stacks --stack-name  upparat-test --query "Stacks[0].Outputs[?OutputKey=='RoleArn'].OutputValue" --output text`
   ```

#### Create AWS IoT Job

1. Upload a test file:

   ```bash
   export UPPARAT_TEST_FILE="<MY_FILE>"
   aws s3 cp ${UPPARAT_TEST_FILE} s3://${UPPARAT_BUCKET_NAME}
   ```

1. Set the following environment variables and run the script:
   ```bash
   export UPPARAT_TEST_THINGS="<COMA-SEPARATED-THING-ARNS>"
   python aws_jobs.py
   ```

#### Cleanup

```bash
aws s3 rm s3://${UPPARAT_BUCKET_NAME} --recursive
aws cloudformation delete-stack --stack-name upparat-test
```
