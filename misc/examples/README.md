# Integration Test Setup

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

### Docker Compose

- `docker-compose run upparat` to run upparat, also starts mosquitto.
- `docker-compose up mosquitto` just mosquitto.

**NOTE:** Keep in mind to stop mosquitto or any other MQTT clients on other devices
to prevent two clients connecting with the same device id.
