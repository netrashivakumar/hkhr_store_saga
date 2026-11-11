FROM jenkins/jenkins:lts-jdk17
USER root
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.3.1.tgz | tar -xz -C /tmp && mv /tmp/docker/docker /usr/local/bin/docker && rm -rf /tmp/docker
RUN curl -fsSLo /usr/local/bin/kubectl https://dl.k8s.io/release/v1.31.0/bin/linux/amd64/kubectl && chmod +x /usr/local/bin/kubectl
USER jenkins
