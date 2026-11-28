FROM python:3.12-slim
RUN python -m pip install --no-cache-dir wcwidth==0.2.13
COPY worker.py /harness/worker.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0
USER 10001:10001
ENTRYPOINT ["python", "/harness/worker.py"]
