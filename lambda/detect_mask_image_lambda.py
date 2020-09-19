from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing.image import img_to_array
from tensorflow.keras.models import load_model
import numpy as np
import cv2
import urllib.parse
import boto3
import botocore
import os

#   MODEL_HOME = /mnt/inference/model
#   PYTHONPATH = /mnt/inference/lib

s3 = boto3.client('s3', 'us-east-1', config=botocore.config.Config(s3={'addressing_style': 'path'}))


# hook for lambda
def handler(event, context):
    file_obj = get_file_from_s3(event)
    mask_image(file_obj, event)


def get_file_from_s3(event):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

    print("[INFO] Fetching Image " + key + " from bucket " + bucket)

    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        print("[INFO] Content Type of the Image: " + response['ContentType'])
        return response['Body']

    except Exception as e:
        print(e)
        print(
            'Error getting object {} from bucket {}. Make sure they exist and your bucket is in the same region as this function.'.format(
                key, bucket))
        raise e


def mask_image(file_obj, event):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    file_content = file_obj.read()

    model_home = os.environ['MODEL_HOME']

    modelname = model_home + "/mask_detector.model"
    confidencefactor = 0.5

    # load our serialized face detector model from disk
    print("[INFO] loading face detector model...")
    prototxtPath = model_home + "/face_detector/deploy.prototxt"
    weightsPath = model_home + "/face_detector/res10_300x300_ssd_iter_140000.caffemodel"
    net = cv2.dnn.readNet(prototxtPath, weightsPath)

    # load the face mask detector model from disk
    print("[INFO] loading face mask detector model...")
    model = load_model(modelname)

    # load the input image from S3, clone it, and grab the image spatial
    # dimensions
    # creating 1D array from bytes data range between[0,255]
    np_array = np.fromstring(file_content, np.uint8)
    # decoding array
    image = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
    print("[INFO] reading image ...")

    orig = image.copy()
    (h, w) = image.shape[:2]

    # construct a blob from the image
    blob = cv2.dnn.blobFromImage(image, 1.0, (300, 300),
                                 (104.0, 177.0, 123.0))

    # pass the blob through the network and obtain the face detections
    print("[INFO] computing face detections...")
    net.setInput(blob)
    detections = net.forward()

    # loop over the detections
    for i in range(0, detections.shape[2]):
        # extract the confidence (i.e., probability) associated with
        # the detection
        confidence = detections[0, 0, i, 2]

        # filter out weak detections by ensuring the confidence is
        # greater than the minimum confidence

        if confidence > confidencefactor:
            print(confidence)
            print("[INFO] Confidence is greater than 0.5...")
            # compute the (x, y)-coordinates of the bounding box for
            # the object
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (startX, startY, endX, endY) = box.astype("int")

            # ensure the bounding boxes fall within the dimensions of
            # the frame
            (startX, startY) = (max(0, startX), max(0, startY))
            (endX, endY) = (min(w - 1, endX), min(h - 1, endY))

            # extract the face ROI, convert it from BGR to RGB channel
            # ordering, resize it to 224x224, and preprocess it
            face = image[startY:endY, startX:endX]
            face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
            face = cv2.resize(face, (224, 224))
            face = img_to_array(face)
            face = preprocess_input(face)
            face = np.expand_dims(face, axis=0)

            print("[INFO] pass the face through the model to determine if the face has a mask or not...")
            # pass the face through the model to determine if the face
            # has a mask or not
            (mask, withoutMask) = model.predict(face)[0]

            # determine the class label and color we'll use to draw
            # the bounding box and text
            label = "Mask" if mask > withoutMask else "No Mask"
            color = (0, 255, 0) if label == "Mask" else (0, 0, 255)

            # include the probability in the label
            label = "{}: {:.2f}%".format(label, max(mask, withoutMask) * 100)

            # display the label and bounding box rectangle on the output
            # frame
            cv2.putText(image, label, (startX, startY - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
            cv2.rectangle(image, (startX, startY), (endX, endY), color, 2)

            # saving image to tmp (writable) directory
            cv2.imwrite("/tmp/" + key.replace("input/", ""), image)

    # upload the output image
    # s3.put_object(Bucket=bucket, Key=key.replace("input","output"), Body=open("/tmp/" + key.replace("input/",""), "rb").read())
    with open("/tmp/" + key.replace("input/", ""), "rb") as f:
        s3.upload_fileobj(f, bucket, key.replace("input", "output"))
    print("[INFO] Image processed and uploaded to " + key.replace("input", "output"))