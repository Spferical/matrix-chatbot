USER=matrixbot
VOLUME=/matrixbot/data/
chown -R $USER $VOLUME && \
exec python3 main.py "$@"
