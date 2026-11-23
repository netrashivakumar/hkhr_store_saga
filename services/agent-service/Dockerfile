FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
ENV MCP_TRANSPORT=http PORT=8000
EXPOSE 8000
CMD ["python", "mcp_server.py"]