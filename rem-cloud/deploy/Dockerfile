FROM ghcr.io/xinnan-tech/xiaozhi-esp32-server:server-base
WORKDIR /opt/xiaozhi-esp32-server
COPY server/ ./
RUN groupadd -g 10001 rem && useradd -u 10001 -g rem -M rem && \
    mkdir -p data tmp && chown -R rem:rem /opt/xiaozhi-esp32-server
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Shanghai
USER 10001:10001
CMD ["python", "rem-entrypoint.py"]
