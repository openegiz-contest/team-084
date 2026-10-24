FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY tynys ./tynys
COPY services ./services
COPY data ./data
WORKDIR /app/services
USER nobody
CMD ["python", "field.py"]
