FROM python:3.8-buster

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD [ "python", "scrapeScenes.py" ]
