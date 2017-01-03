USER=matrixbot
VOLUME=/matrixbot/data/
chown -R $USER $VOLUME && \
exec python2 main.py "$@"
