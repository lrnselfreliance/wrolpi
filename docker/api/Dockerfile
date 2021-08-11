FROM python:3.9
ENV DOCKER=true

WORKDIR /opt/wrolpi

# Install dependencies
RUN apt update
RUN apt install -y ffmpeg wkhtmltopdf

# Copy minimal directories/files
COPY main.py config *local.yaml alembic.ini /opt/wrolpi/
COPY api /opt/wrolpi/api

# Install all requirements files.
COPY requirements.txt /opt/wrolpi/
RUN find -name requirements.txt -exec pip install --upgrade -r {} \;

# Run the webserver
ENTRYPOINT [ "python3", "/opt/wrolpi/main.py"]
CMD ["api", "--host", "0.0.0.0" ]
