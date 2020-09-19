import json
import base64
import boto3
import uuid
import time


def write_to_file(save_path, data):
    with open(save_path, "wb") as f:
        f.write(base64.b64decode(data))


def handler(event, context):
    id = str(uuid.uuid1()) + ".jpg"

    write_to_file("/tmp/" + id, event["body"])

    bucket = 'skillenza-hackathon-mask-detection-image'
    file_path = 'input/' + id
    s3 = boto3.client('s3')
    try:
        with open("/tmp/" + id, "rb") as f:
            s3.upload_fileobj(f, bucket, file_path)
    except Exception as e:
        raise IOError(e)

    return {
        "statusCode": 200,
        "headers": {
            "content-type": "image/jpeg"
        },
        "body": event["body"],
        "isBase64Encoded": True
    }