FROM python:3.11-slim

# 不写 .pyc、日志直出，便于容器内排障
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先单独安装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# 容器内固定监听 8000；宿主机端口通过 compose 的 APP_PORT 映射
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
