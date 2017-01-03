from debian

run apt-get update && \
	apt-get install -y \
	python \
	python-pip \
	git

env MATRIX_CHATBOT_CONFIG "/matrixbot/data/config.cfg"
env MATRIX_CHATBOT_BRAIN "/matrixbot/data/brain.txt"

run useradd matrixbot

workdir /matrixbot

volume /matrixbot/data/

copy ./*.py requirements.txt docker_entrypoint.sh /matrixbot/

run pip install -r requirements.txt

cmd [ "sh", "docker_entrypoint.sh" ]
