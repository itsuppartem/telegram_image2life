FROM python:3.12

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY .env .
COPY . .

CMD ["python", "workers.py"]