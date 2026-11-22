FROM python:3.12-slim

WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
# mocks : faux Stocks, utilisé tant que le vrai service Stocks n'est pas livré
COPY mocks ./mocks

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
