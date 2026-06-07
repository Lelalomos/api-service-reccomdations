import json
import os
import time
import uuid

import pika

from rabbitmq.rabbitmq_setup import DEFAULT_QUEUE, declare_queue, get_connection
from service_logging import get_logger


DEFAULT_RPC_TIMEOUT_SECONDS = float(os.getenv("API_RPC_TIMEOUT_SECONDS", "30"))
logger = get_logger(__name__, "api-service")


class RpcTimeoutError(RuntimeError):
    pass


class RpcWorkerError(RuntimeError):
    pass


def request_recommendations(username: str, title: str, timeout_seconds: float = DEFAULT_RPC_TIMEOUT_SECONDS) -> list[dict]:
    connection = get_connection()
    try:
        channel = connection.channel()
        declare_queue(channel, DEFAULT_QUEUE)

        callback_queue = channel.queue_declare(queue="", exclusive=True).method.queue
        correlation_id = str(uuid.uuid4())
        response_body: dict[str, object] | None = None

        def on_response(
            ch: pika.adapters.blocking_connection.BlockingChannel,
            method: pika.spec.Basic.Deliver,
            properties: pika.BasicProperties,
            body: bytes,
        ) -> None:
            nonlocal response_body
            if properties.correlation_id != correlation_id:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                return

            response_body = json.loads(body.decode("utf-8"))
            logger.info(
                "rpc_response_received correlation_id=%s status=%s",
                correlation_id,
                response_body.get("status"),
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            ch.stop_consuming()

        consumer_tag = channel.basic_consume(
            queue=callback_queue,
            on_message_callback=on_response,
            auto_ack=False,
        )
        channel.basic_publish(
            exchange="",
            routing_key=DEFAULT_QUEUE,
            body=json.dumps({"username": username, "movie": title}).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=pika.DeliveryMode.Persistent,
                reply_to=callback_queue,
                correlation_id=correlation_id,
            ),
        )
        logger.info(
            "rpc_request_sent correlation_id=%s username=%s title=%s queue=%s timeout_seconds=%s",
            correlation_id,
            username,
            title,
            DEFAULT_QUEUE,
            timeout_seconds,
        )

        deadline = time.time() + timeout_seconds
        while time.time() < deadline and response_body is None:
            connection.process_data_events(time_limit=1)

        if response_body is None:
            channel.basic_cancel(consumer_tag)
            logger.warning(
                "rpc_request_timeout correlation_id=%s username=%s title=%s timeout_seconds=%s",
                correlation_id,
                username,
                title,
                timeout_seconds,
            )
            raise RpcTimeoutError(f"Worker did not respond within {timeout_seconds} seconds.")

        if response_body.get("status") != "done":
            logger.warning(
                "rpc_request_failed correlation_id=%s username=%s title=%s",
                correlation_id,
                username,
                title,
            )
            raise RpcWorkerError(str(response_body.get("error") or "Worker failed to process the request."))

        recommendations = response_body.get("recommendations")
        if not isinstance(recommendations, list):
            raise RpcWorkerError("Worker response is missing recommendations.")

        return recommendations
    finally:
        connection.close()
