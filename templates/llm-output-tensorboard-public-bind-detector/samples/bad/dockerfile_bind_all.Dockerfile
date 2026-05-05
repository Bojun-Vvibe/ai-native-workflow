# Bad: canonical "Dockerize TensorBoard" snippet. JSON-array CMD form
# with --bind_all is the most common shape an LLM emits when asked
# "give me a Dockerfile for TensorBoard".
FROM python:3.11-slim
RUN pip install --no-cache-dir tensorboard
EXPOSE 6006
CMD ["tensorboard", "--logdir=/logs", "--bind_all", "--port=6006"]
