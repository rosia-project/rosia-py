FROM ros:humble

RUN apt-get update && apt-get install -y \
    ros-humble-turtlesim \
    ros-humble-rqt-graph \
    python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc

RUN pip install --upgrade pip setuptools && \
    pip install numpy ray[default] matplotlib rerun-sdk pyelk pyzmq cloudpickle rich

COPY . /rosia-src
RUN pip install /rosia-src

WORKDIR /benchmark

COPY benchmark/benchmarks/ ./

CMD ["bash", "-c", "source /opt/ros/humble/setup.bash && python3 run_benchmarks.py"]
