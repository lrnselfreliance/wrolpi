FROM python:3.8-buster
ENV DOCKER=true
WORKDIR /opt/wrolpi

# Update dependencies for the services install.
RUN apt update
# ffmpeg for Videos and Latex for OTP PDF.
RUN apt-get install -y ffmpeg texlive-latex-base
RUN pdflatex --version

# Install WROLPi
COPY main.py /opt/wrolpi/
COPY config /opt/wrolpi/config
COPY wrolpi /opt/wrolpi/wrolpi
COPY modules /opt/wrolpi/modules
COPY requirements.txt /opt/wrolpi/requirements.txt
RUN pip3 install -r /opt/wrolpi/requirements.txt

ENTRYPOINT [ "python3", "/opt/wrolpi/main.py"]
CMD ["api", "--host", "0.0.0.0" ]
