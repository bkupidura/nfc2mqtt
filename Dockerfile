FROM python:3-alpine

WORKDIR /nfc2mqtt

COPY . .
RUN apk update && \
        apk add libusb-dev git build-base libffi-dev openssl-dev cargo
RUN pip install .

CMD ["nfc2mqtt", "-c", "/config.yaml"]
