# set base image (host OS)
FROM python:3.14.7

# Install some utilities
RUN export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get install -y --fix-missing \
    jq \
    nano \
    less

# flag for being in docker
ENV VDJ_DOCKER=1

# System deps:
RUN pip install uv pyyaml
RUN uv tool install --with jinja2-time copier
RUN uv tool install rust-just
ENV PATH=/root/.local/bin:$PATH

# set the working directory in the container
WORKDIR /work

# RUN pip install schema-automator
# RUN pip install appengine-python-standard
# RUN pip install cruft
# 
# # AIRR requirements
# RUN pip install airr
# 
# RUN mkdir /ak-etvl
# COPY . /ak-etvl
# 
# RUN cd /ak-etvl/ak-schema && make install
