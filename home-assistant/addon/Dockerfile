FROM python:3.13-alpine
RUN apk add --no-cache tzdata
WORKDIR /app
COPY app/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ /app/
CMD ["python3", "-u", "/app/ha_ingress.py"]
