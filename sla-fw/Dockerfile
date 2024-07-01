FROM ubuntu:jammy

ENV TZ=Etc/UTC
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install native deps
RUN apt-get update && apt-get install -y python3 python3-pip python3-paho-mqtt python3-systemd python3-serial python3-numpy python3-pydbus python3-gi python3-bitstring python3-toml python3-mock python3-future \
git openssh-client build-essential xxd gawk gettext python3-coverage python3-networkmanager python3-dbusmock python3-pil python3-distro python3-sphinx python3-psutil python3-deprecated python3-deprecation python3-evdev lftp \
python3-pyinotify inotify-tools python3-aiohttp python3-yaml libwayland-dev pkg-config graphviz black python3-cairo python3-gi-cairo librsvg2-dev

# Install python deps
RUN pip3 install gpio gpiod readerwriterlock pylint==2.13.9 pysignal pywayland smbus2 mypy==0.960 types-toml

# Create use that will run the build
RUN useradd --create-home --user-group appuser
USER appuser
WORKDIR /home/appuser/

# Setup ssh to trust git server
RUN mkdir -p .ssh
RUN chmod 700 .ssh
RUN ssh-keyscan gitlab.com >> .ssh/known_hosts

