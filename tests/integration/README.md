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

### Jobs

To use AWS Iot jobs with pre-signed S3 URLs create the following:
1. A S3 bucket (`<MY_BUCKET>`) where the files to be downloaded are stored
1. A IoT role to sign the download URL with the following policy:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "s3:GetObject",
         "Resource": "arn:aws:s3:::<MY_BUCKET>/*"
       }
     ]
   }
   ```
1. Set the following environment variables and run the script:
   ```bash
   export THINGS="<COMA-SEPARATED-THING-ARNS>"
   export S3_FILE_URL="<S3-URL-OF-FILE>"
   export S3_ROLE_ARN="<SIGNER_ROLE_ARN>"
   python aws_jobs.py
   ```

### Docker Compose

- `docker-compose run upparat` to run upparat, also starts mosquitto.
- `docker-compose up mosquitto` just mosquitto.


**NOTE:** Keep in mind to stop mosquitto or any other MQTT clients on other devices 
to prevent two clients connecting with the same device id.
