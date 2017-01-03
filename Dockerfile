from python:2-alpine

env MATRIX_CHATBOT_CONFIG "/matrixbot/data/config.cfg"
env MATRIX_CHATBOT_BRAIN "/matrixbot/data/brain.txt"

run adduser -S matrixbot

workdir /matrixbot

volume /matrixbot/data/

copy ./*.py requirements.txt docker_entrypoint.sh /matrixbot/

run pip install -r requirements.txt

cmd [ "sh", "docker_entrypoint.sh" ]
