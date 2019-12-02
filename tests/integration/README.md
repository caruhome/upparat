# Integration Test Setup

### Mosquitto

1. Install [mosquitto](https://mosquitto.org/download/)

1. Create an AWS IoT thing and save the certificate (as `certificate.pem.crt`), 
the private key (as `private.pem.key`) and the [AWS root certificate](https://www.amazontrust.com/repository/AmazonRootCA1.pem) (as `root.pem`) to the 
[mosquitto](./mosquitto) folder.

   **Note**: Do not forget to activate the certificate.
   
1. Create a policy and attach it to your device:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "iot:Connect",
          "Resource": ["*"]
       },
       {
         "Effect": "Allow",
         "Action": "iot:Publish",
         "Resource": [
            "arn:aws:iot:<REGION>:<ACCOUNT_ID>:topic/$aws/things/${iot:ClientId}/jobs/*"
          ]
        },
        {
          "Effect": "Allow",
          "Action": "iot:Subscribe",
          "Resource": [
            "arn:aws:iot:<REGION>:<ACCOUNT_ID>:topicfilter/$aws/things/${iot:ClientId}/jobs/*"            
          ]
        },
        {
          "Effect": "Allow",
          "Action": "iot:Receive",
          "Resource": [
            "arn:aws:iot:<REGION>:<ACCOUNT_ID>:topic/$aws/things/${iot:ClientId}/jobs/*"
          ]
        }
      ]
    }
   ```
   
1. Copy _[mosquitto/aws-bridge.conf.tmpl](mosquitto/aws-bridge.conf.tmpl)_ to _mosquitto/aws-bridge.conf_
   and replace the `@BASE_DIR@` and `@DEVICE_ID@` placeholders:
   
        THING_NAME=YOUR_THING_NAME
        BROKER=YOUR_BROKER_HOST
        cp mosquitto/aws-bridge.conf.tmpl mosquitto/aws-bridge.conf
        sed -i -e "s|@THING_NAME@|${THING_NAME}|g" mosquitto/aws-bridge.conf
        sed -i -e "s|@BROKER@|${BROKER}|g" mosquitto/aws-bridge.conf
        sed -i -e "s|@BASE_DIR@|${PWD}|g" mosquitto/aws-bridge.conf
        
1. Start mosquitto: `mosquitto -v -c mosquitto/aws-bridge.conf`

### Upparat

1. Copy _[upparat/config.ini.tmpl](upparat/config.ini.tmpl)_ to _./config.ini_ and replace the `@DEVICE_ID@` placeholder:
        
        THING_NAME=YOUR_THING_NAME
        cp upparat/config.ini.tmpl upparat/config.ini
        sed -i -e "s|@THING_NAME@|${THING_NAME}|g" upparat/config.ini
        sed -i -e "s|@BASE_DIR@|${PWD}|g" upparat/config.ini

1. Start upparat: `upparat -c upparat/config.ini`

### Test Jobs
To use AWS Iot jobs with pre-signed S3 URLs create a S3 bucket and a corresponding role.

#### AWS CloudFormation Setup
1. Install [AWS CLI](https://aws.amazon.com/cli/)
1. Deploy stack:
   ```bash
   aws cloudformation deploy --template-file upparat-test.yml --capabilities CAPABILITY_IAM --stack-name upparat-test   
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
