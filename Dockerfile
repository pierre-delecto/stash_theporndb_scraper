FROM python:alpine3.7
COPY . /app
WORKDIR /app
RUN apk add --no-cache --virtual .build-deps gcc libc-dev libxslt-dev && \
    apk add --no-cache libxslt git jpeg-dev zlib-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir flask && \
    apk del .build-deps && rm -rf requirements.txt
EXPOSE 6969

ENTRYPOINT [ "python" ]

CMD [ "tpdb.py" ]