FROM python:3.12-slim
RUN python -m pip install --no-cache-dir pytest==8.3.5 hypothesis==6.131.9 pytest-mock==3.14.0 pytest-cov==6.0.0 pretend==1.0.9 six==1.17.0 attrs==25.3.0 rpds-py==0.24.0 referencing==0.36.2 jsonschema-specifications==2025.4.1 python-dateutil==2.9.0.post0 pytz==2025.2 more-itertools==10.7.0 tomli==2.2.1 toml==0.10.2 requests==2.32.3 packaging==24.2 typing_extensions==4.13.2
COPY trace_plugin.py /harness/trace_plugin.py
COPY worker.py /harness/worker.py
COPY core.py /harness/core.py
RUN pip install setuptools==80.9.0

