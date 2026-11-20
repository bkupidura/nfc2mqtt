FROM python:3.14-alpine

WORKDIR /nfc2mqtt

RUN apk add --no-cache libusb

COPY . .
RUN pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install --no-cache-dir .

CMD ["nfc2mqtt", "-c", "/config.yaml"]
