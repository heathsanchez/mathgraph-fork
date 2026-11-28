FROM python:3.12.14-slim
RUN pip install --no-cache-dir pytest==7.4.3 whatever==0.7
COPY worker.py /worker.py
USER 65534:65534
WORKDIR /target
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0
ENTRYPOINT ["python", "-B", "/worker.py"]
