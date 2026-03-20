FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code and static assets mounted via volume at runtime
EXPOSE 8378

CMD ["python", "-m", "src.dashboard"]
