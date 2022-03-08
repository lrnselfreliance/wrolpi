FROM python:3.8-buster
ENV DOCKER=true
WORKDIR /opt/wrolpi

# Update dependencies for the services install.
RUN apt update
# ffmpeg for Videos and Latex for OTP PDF.  osm2pgsql to import map files.
RUN apt-get install -y ffmpeg texlive-latex-base texlive-latex-extra
RUN pdflatex --version
RUN ffmpeg -version

# Install WROLPi
COPY main.py /opt/wrolpi/
COPY wrolpi /opt/wrolpi/wrolpi
COPY modules /opt/wrolpi/modules
COPY requirements.txt /opt/wrolpi/requirements.txt
RUN pip3 install -r /opt/wrolpi/requirements.txt

ENTRYPOINT [ "python3", "/opt/wrolpi/main.py"]
CMD ["api", "--host", "0.0.0.0" ]
